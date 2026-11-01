"""Edições feitas pelo usuário em um estado da simulação (algoritmo, CPUs e tarefas)."""
from copy import deepcopy
from types import SimpleNamespace

from processor import processor
from TCB import TCB, NEW, READY, RUNNING, SUSPENDED, FINISHED, REMOVED
from simulation_result import Event, TaskInfo, SystemEvent
from choose_task import get_algorithm, normalize_algorithm
from task_fields import TASK_FIELDS, positive_integer, validate_changes

# Estados que o usuário pode escolher na interface (REMOVED só é alcançado removendo a tarefa)
TASK_STATES = (NEW, READY, RUNNING, SUSPENDED, FINISHED)


# Aplica uma edição numa cópia do estado e devolve a cópia.
# Se qualquer parte for inválida, levanta ValueError e o estado original fica intacto
# (a edição é "tudo ou nada"). Os parâmetros são opcionais: só os informados são aplicados.
#   algorithm       nome do algoritmo ("RM" ou "EDF")
#   num_cpus        nova quantidade de CPUs
#   task_id         tarefa a editar, junto com:
#       changes     dicionário campo -> valor (ver TASK_FIELDS)
#       task_state  novo estado da tarefa (um de TASK_STATES)
#   add_task        dicionário com os campos de uma nova tarefa (inclui o "id")
#   remove_task_id  ID da tarefa a remover
def edit_state(state, algorithm=None, num_cpus=None, task_id=None, changes=None, task_state=None,
               add_task=None, remove_task_id=None):
    edited = deepcopy(state)
    descriptions = []
    if algorithm is not None:
        set_algorithm(edited, algorithm)
        descriptions.append(f"algoritmo {edited.algorithm}")
    if num_cpus is not None:
        count = set_num_cpus(edited, num_cpus)
        descriptions.append(f"{count} processador(es)")
    if task_id is not None:
        edit_task(edited, task_id, changes or {}, task_state)
        descriptions.append(f"tarefa {task_id}")
    elif changes or task_state is not None:
        raise ValueError("Selecione uma tarefa antes de aplicar alterações.")
    if add_task is not None:
        added = include_task(edited, add_task)
        descriptions.append(f"tarefa {added.id} incluída")
    if remove_task_id is not None:
        remove_task(edited, remove_task_id)
        descriptions.append(f"tarefa {remove_task_id} removida")

    edited.reschedule_needed |= edit_requires_rescheduling(state, edited)
    edited.refresh_result()
    if descriptions:
        edited.log.append(f"[Edição no instante {edited.tick}] " + ", ".join(descriptions) + ".")
    return edited


# ---------- Sistema: algoritmo e CPUs ----------

# Troca o algoritmo a partir do instante atual.
def set_algorithm(state, name):
    value = normalize_algorithm(name)
    if value != state.algorithm:
        state.result.system_events.append(SystemEvent(state.tick, f"Algoritmo {state.algorithm} → {value}"))
    state.algorithm = value


# Muda a quantidade de CPUs. Tarefas que estavam em CPUs removidas voltam para a fila de prontos.
# Devolve a nova quantidade.
def set_num_cpus(state, value):
    count = positive_integer(value, "Número de processadores")
    if count != len(state.processors_list):
        state.result.system_events.append(SystemEvent(
            state.tick, f"Processadores: {len(state.processors_list)} → {count}"))

    for cpu in state.processors_list[count:]:
        if cpu.task_running is not None:
            state.change_state(cpu.task_running, READY)
    state.processors_list = state.processors_list[:count]

    while len(state.processors_list) < count:
        state.processors_list.append(processor(len(state.processors_list) + 1))
    return count


# Diz se a edição pode mudar quem deve executar (e portanto exige chamar o algoritmo).
# Sem tarefas prontas não há alternativa a despachar nem a preemptar.
def edit_requires_rescheduling(before, after):
    if len(after.tasks_in(READY)) == 0:
        return False
    if before.algorithm != after.algorithm:
        return True
    if len(after.processors_list) > len(before.processors_list):
        return True
    if running_instances(before) != running_instances(after):
        return True

    # Remover só uma tarefa que já esperava não altera quem executa;
    # incluir uma candidata ou mudar a prioridade de alguma pode alterar.
    old_priorities = priorities(before)
    new_priorities = priorities(after)
    for key, value in new_priorities.items():
        if key not in old_priorities or value != old_priorities[key]:
            return True
    return False


# Conjunto de (tarefa, instância) que estão executando.
def running_instances(state):
    return {(task.id, task.instance_number) for task in state.tasks_in(RUNNING)}


# Resume a prioridade de cada instância candidata segundo o algoritmo do estado.
def priorities(state):
    values = {}
    policy = get_algorithm(state.algorithm)
    for task in state.tasks_in(READY) + state.tasks_in(RUNNING):
        values[(task.id, task.instance_number)] = policy.priority_signature(task)
    return values


# ---------- Tarefas: edição de características e de estado ----------

# Traduz o nome do estado digitado (sem diferenciar maiúsculas) para um de TASK_STATES.
def parse_task_state(task_state):
    if task_state is None:
        return None
    text = str(task_state).strip().casefold()
    for name in TASK_STATES:
        if name.casefold() == text:
            return name
    raise ValueError("Estado inválido. Escolha Nova, Pronta, Executando, Suspensa ou Finalizada.")


# Edita a família inteira (todas as instâncias ainda não concluídas) de uma tarefa.
def edit_task(state, task_id, changes, task_state):
    if state.is_removed(task_id):
        raise ValueError("A tarefa foi removida. Retroceda a simulação para restaurá-la.")
    task, source = state.current_task(task_id)
    target = parse_task_state(task_state)

    values = validate_changes(task, changes)
    check_unique_color(state, values['color'], task_id)
    if source == FINISHED and target not in (None, FINISHED):
        raise ValueError("Uma instância finalizada não pode ser reaberta. Retroceda a simulação para editá-la antes do término.")

    siblings = state.active_instances(task_id)
    if not siblings:
        siblings = [task]
    arrival_changed = values['arrival'] != task.arrival
    if arrival_changed and any(other.state != NEW for other in siblings):
        raise ValueError("O ingresso de uma instância dessa tarefa já ocorreu. Retroceda até todas estarem Novas para alterá-lo.")

    changed_fields = [key for key, value in values.items() if value != getattr(task, key)]
    state_changed = family_state_differs(siblings, source, target)
    if changed_fields or state_changed:
        log_task_changes(state, task_id, task, values, changed_fields, state_changed, target)
    check_duration(siblings, values["duration"], target)

    apply_values(task, siblings, values, changed_fields, arrival_changed)
    info = state.info_of(task_id)
    for key in TASK_FIELDS:
        setattr(info, key, deepcopy(values[key]))

    if target is not None:
        set_family_state(state, siblings, target)


# Impede duas tarefas com a mesma cor (cada tarefa precisa de uma cor diferente).
def check_unique_color(state, color, task_id):
    for info in state.result.tasks:
        if info.id != task_id and info.color.upper() == color.upper():
            raise ValueError(f"A cor {color} já é usada por outra tarefa. Cada tarefa precisa de uma cor diferente.")


# Diz se o estado pedido é diferente do estado atual de alguma instância da família.
def family_state_differs(siblings, source, target):
    if target is None:
        return False
    if source != target:
        return True
    for other in siblings:
        if other.starts_suspended != (target == SUSPENDED):
            return True
        if other.state != NEW and other.state != target:
            return True
    return False


# Registra no gráfico (evento S#) o que mudou na tarefa.
def log_task_changes(state, task_id, task, values, changed_fields, state_changed, target):
    names = dict(color='cor', arrival='ingresso', duration='duração', period='período', deadline='prazo')
    details = []
    for key in changed_fields:
        if key == 'events':
            details.append(f"eventos: {len(task.events)} → {len(values[key])}")
        else:
            details.append(f"{names[key]}: {getattr(task, key)} → {values[key]}")
    detail = ", ".join(details)
    if state_changed:
        detail = (detail + "; " if detail else "") + f"estado global → {target} (ativas e futuras)"
    state.result.system_events.append(SystemEvent(state.tick, f"Tarefa {task_id}: {detail}"))


# A nova duração precisa superar o que cada instância já executou
# (pode ser igual somente se a instância está sendo finalizada).
def check_duration(siblings, duration, target):
    for other in siblings:
        finishing = target == FINISHED or other.state == FINISHED
        if duration < other.computational_time or (duration == other.computational_time and not finishing):
            raise ValueError(f"A duração deve superar os {other.computational_time} ticks já executados pela instância {other.instance_number}, ou ser igual ao finalizar a instância.")


# Copia os novos valores para todas as instâncias da família e recalcula seus prazos.
# Ingressos já ocorridos e o trabalho já executado não são reescritos.
def apply_values(task, siblings, values, changed_fields, arrival_changed):
    for other in siblings:
        for key in ("color", "duration", "period", "deadline", "events"):
            setattr(other, key, deepcopy(values[key]))
        if other.state == NEW and (arrival_changed or 'period' in changed_fields):
            other.arrival = values["arrival"] + (other.instance_number - task.instance_number) * values["period"]
        other.end_period = other.arrival + other.period
        other.absolute_deadline = other.arrival + other.deadline


# Confere se a família pode ir para o estado pedido (Nova ou Executando têm condições).
def check_target_state(state, siblings, target):
    if target == NEW:
        if any(task.computational_time for task in siblings):
            raise ValueError("Uma instância dessa tarefa já executou e não pode voltar a Nova. Retroceda a simulação.")
        if any(task.arrival < state.tick for task in siblings):
            raise ValueError("Todas as instâncias Novas precisam ter ingresso no instante atual ou no futuro.")

    if target == RUNNING:
        admitted = [task for task in siblings if task.arrival <= state.tick and task.state != FINISHED]
        if not admitted:
            raise ValueError("A tarefa ainda não chegou. Antecipe o ingresso enquanto ela estiver Nova ou avance o relógio.")
        needed = sum(task.state != RUNNING for task in admitted)
        free = sum(cpu.task_running is None for cpu in state.processors_list)
        if needed > free:
            raise ValueError(f"Processadores ocupados: são necessárias {needed} CPUs livres para executar todas as instâncias ativas, mas há {free}. Aumente a quantidade ou libere CPUs.")


# Muda todas as instâncias da família para o estado pedido.
# Instâncias futuras continuam Novas (só herdam o estado quando chegarem).
def set_family_state(state, siblings, target):
    check_target_state(state, siblings, target)

    for task in siblings:
        if task.state == FINISHED:
            continue
        task.starts_suspended = (target == SUSPENDED)
        future = task.state == NEW and task.arrival > state.tick
        if future and target != FINISHED:
            continue
        if task.state == target:
            continue
        move_task(state, task, target, future)

    already_finished = any(task.id == siblings[0].id and task.state == FINISHED for task in state.all_tasks)
    if target == FINISHED and not already_finished:
        # Uma definição cancelada antes do primeiro ingresso continua
        # consultável, sem registrar chegada/término que nunca aconteceram.
        representative = min(siblings, key=lambda task: task.instance_number)
        if representative not in state.all_tasks:
            state.all_tasks.append(representative)
        state.change_state(representative, FINISHED)


# Move uma instância para o estado pedido, registrando os eventos do gráfico.
def move_task(state, task, target, future):
    if future:
        # Finalizar a família cancela as liberações que ainda não ocorreram.
        state.discard(task)
        return

    if target == NEW:
        # Desfaz a chegada registrada neste mesmo instante
        state.result.events = [event for event in state.result.events
                               if not (event.kind == 'arrival' and event.tick == state.tick
                                       and event.task_id == task.id and event.instance == task.instance_number)]
    else:
        if not arrival_recorded(state, task):
            state.result.events.append(Event('arrival', state.tick, task.id, task.instance_number))
        if target != FINISHED:
            state.enqueue_next_instance(task)

    state.change_state(task, target)
    if target == RUNNING:
        cpu = next(cpu for cpu in state.processors_list if cpu.task_running is None)
        task.processor = cpu
        cpu.task_running = task
    elif target == FINISHED:
        state.result.events.append(Event('finish', state.tick, task.id, task.instance_number))


# Diz se a chegada desta instância já está registrada nos eventos.
def arrival_recorded(state, task):
    for event in state.result.events:
        if event.kind == 'arrival' and event.task_id == task.id and event.instance == task.instance_number:
            return True
    return False


# ---------- Tarefas: incluir e remover ----------

# Inclui uma definição periódica no instante atual, sem reescrever o passado.
def include_task(state, fields):
    task_id = positive_integer(fields.get('id', ''), 'Identificador')
    if any(key not in ('id',) + TASK_FIELDS for key in fields):
        raise ValueError("A inclusão contém um campo de tarefa desconhecido.")
    if any(info.id == task_id for info in state.result.tasks):
        raise ValueError("Este identificador já pertence ao histórico. Escolha um novo ID.")

    defaults = dict(color='000001', arrival=state.tick, duration=1, period=4, deadline=4, events=[])
    defaults.update({key: value for key, value in fields.items() if key in TASK_FIELDS})
    values = validate_changes(SimpleNamespace(**defaults), {})
    if values['arrival'] < state.tick:
        raise ValueError("O ingresso de uma nova tarefa não pode estar no passado.")
    check_unique_color(state, values['color'], task_id)

    task = TCB([str(task_id)] + [str(values[key]) for key in TASK_FIELDS[:-1]] + [repr(values['events'])])
    state.append_task(task)
    state.result.tasks.append(TaskInfo(task))
    state.result.system_events.append(SystemEvent(state.tick, f"Tarefa {task_id} incluída; ingresso {task.arrival}"))
    return task


# Cancela todas as instâncias restantes da definição, preservando as concluídas.
def remove_task(state, task_id):
    if state.is_removed(task_id) or not any(info.id == task_id for info in state.result.tasks):
        raise ValueError("Selecione uma tarefa existente que ainda não foi removida.")
    cancelled = state.active_instances(task_id)
    for task in cancelled:
        state.change_state(task, REMOVED)
    state.info_of(task_id).removed_tick = state.tick
    state.result.events.append(Event('remove', state.tick, task_id, 0))
    state.result.system_events.append(SystemEvent(
        state.tick, f"Tarefa {task_id} removida; {len(cancelled)} instância(s) cancelada(s)"))
