"""Retratos e transações do debugger com calendário, filas e vínculos de CPU."""
import ast
from copy import deepcopy
import random
import re
from types import SimpleNamespace

from processor import processor
from TCB import TCB
from simulation_result import Event, TaskInfo, SystemEvent, SIMULATION_LIMIT
from choose_task import available_algorithms, get_algorithm, normalize_algorithm


TASK_STATES = ("Nova", "Pronta", "Executando", "Suspensa", "Finalizada")
TASK_FIELDS = ("color", "arrival", "duration", "period", "deadline", "events")


# Um retrato completo da simulação em um instante de tempo.
class simulation_state:
    """Fotografia completa das filas, CPUs, calendário, resultados e sorteios de um instante."""
    def __init__(self, algorithm, processors_list, tasks_to_arrival, result):
        """Inicializa os dados de simulation_state com vínculos e valores próprios deste objeto."""
        self.tick = 0
        self.algorithm = algorithm
        self.processors_list = processors_list
        self.tasks_to_arrival = tasks_to_arrival
        self.ready_queue = []
        self.running_tasks = []
        self.suspended_tasks = []
        # Guarda todas as instâncias concluídas, inclusive por edição manual.
        self.terminated_tasks = []
        self.removed_tasks = []
        self.removed_task_ids = set()
        self.result = result
        self.log = ""
        self.random_state = random.getstate()
        # Eventos no limite de um tick são consumidos no próximo despacho,
        # antes de executar o intervalo que começa nesse mesmo instante.
        self.reschedule_needed = False

    def task_queues(self):
        """Centraliza as filas para consulta, cópia e alterações de ciclo de vida."""
        return (("Nova", self.tasks_to_arrival), ("Pronta", self.ready_queue),
                ("Executando", self.running_tasks), ("Suspensa", self.suspended_tasks),
                ("Finalizada", self.terminated_tasks), ("Removida", self.removed_tasks))

    def current_task(self, task_id):
        # O número da instância mantém a ordem de criação mesmo após editar o ingresso.
        """Escolhe a instância ativa mais antiga ou a última concluída para inspeção."""
        if task_id in self.removed_task_ids:
            cancelled = [task for task in self.removed_tasks if task.id == task_id]
            if cancelled:
                return min(cancelled, key=lambda task: task.instance_number), "Removida"
            history = [task for task in self.terminated_tasks if task.id == task_id]
            if history:
                return max(history, key=lambda task: task.instance_number), "Removida"
        active = [(task, name) for name, queue in self.task_queues() if name not in ("Finalizada", "Removida")
                  for task in queue if task.id == task_id]
        if active:
            return min(active, key=lambda item: item[0].instance_number)
        completed = [task for task in self.terminated_tasks if task.id == task_id]
        if completed:
            return max(completed, key=lambda task: task.instance_number), "Finalizada"
        raise ValueError(f"A tarefa {task_id} não existe no estado atual.")

    @property
    def is_finished(self):
        """Indica ausência de trabalho ativo ou futuro; suspensão não é conclusão."""
        return not (self.tasks_to_arrival or self.ready_queue or self.running_tasks
                    or self.suspended_tasks)

    @property
    def is_blocked(self):
        # Suspensão manual não possui um instante de retomada automática.
        """Detecta espera exclusiva por retomada manual, sem liberação futura pendente."""
        return bool(self.suspended_tasks and not
                    (self.tasks_to_arrival or self.ready_queue or self.running_tasks))

    def enqueue_next_instance(self, task):
        """Agenda a próxima liberação por período, sem duplicar ou ultrapassar dez instâncias."""
        if task.instance_number >= SIMULATION_LIMIT or task.id in self.removed_task_ids:
            return None
        next_number = task.instance_number + 1
        # Uma edição ou admissão manual pode já ter agendado a próxima liberação.
        if any(other.id == task.id and other.instance_number == next_number
               for _, queue in self.task_queues() for other in queue):
            return None
        next_instance = task.create_next_instance()
        self.tasks_to_arrival.append(next_instance)
        return next_instance

    def refresh_result(self):
        """Atualiza somente os metadados correntes usados pelo desenho."""
        self.result.algorithm = self.algorithm
        self.result.num_cpus = len(self.processors_list)
        self.result.current_suspended = [(task.id, task.instance_number)
                                         for task in self.suspended_tasks]

    @property
    def algorithm_options(self):
        """Consulta o registro compartilhado, sem nomes concretos fixos na interface."""
        return available_algorithms()

    def edit(self, *, algorithm=None, num_cpus=None, task_id=None, changes=None, task_state=None,
             add_task=None, remove_task_id=None):
        # A transação trabalha numa cópia. Erros nunca deixam filas/CPUs pela metade,
        # e os estados anteriores do histórico permanecem intocados.
        """Aplica uma transação numa cópia; qualquer erro descarta todas as mudanças."""
        edited = deepcopy(self)
        descriptions = []
        if algorithm is not None:
            value = normalize_algorithm(algorithm)
            if value != edited.algorithm:
                edited.result.system_events.append(SystemEvent(edited.tick, f"Algoritmo {edited.algorithm} → {value}"))
            edited.algorithm = value
            descriptions.append(f"algoritmo {value}")
        if num_cpus is not None:
            count = positive_integer(num_cpus, "Número de processadores")
            if count != len(edited.processors_list):
                edited.result.system_events.append(SystemEvent(edited.tick,
                    f"Processadores: {len(edited.processors_list)} → {count}"))
            for cpu in edited.processors_list[count:]:
                if cpu.task_running is not None:
                    task = cpu.task_running
                    edited.running_tasks.remove(task)
                    task.processor = None
                    edited.ready_queue.append(task)
                    cpu.task_running = None
            edited.processors_list = edited.processors_list[:count]
            while len(edited.processors_list) < count:
                edited.processors_list.append(processor(len(edited.processors_list) + 1))
            descriptions.append(f"{count} processador(es)")
        if task_id is not None:
            edited._edit_task(task_id, changes or {}, task_state)
            descriptions.append(f"tarefa {task_id}")
        elif changes or task_state is not None:
            raise ValueError("Selecione uma tarefa antes de aplicar alterações.")
        if add_task is not None:
            added = edited._add_task(add_task)
            descriptions.append(f"tarefa {added.id} incluída")
        if remove_task_id is not None:
            edited._remove_task(remove_task_id)
            descriptions.append(f"tarefa {remove_task_id} removida")
        edited.reschedule_needed |= self._edit_requires_rescheduling(edited)
        edited.refresh_result()
        if descriptions:
            edited.log += f"[Edição no instante {edited.tick}] " + ", ".join(descriptions) + ".\n"
        return edited

    def _edit_requires_rescheduling(self, edited):
        # Sem tarefas prontas não há alternativa a despachar ou a preemptar.
        # Cores, eventos do projeto B e alterações futuras não mudam a decisão.
        """Detecta alterações que podem mudar a seleção, sem executar o escalonador."""
        if not edited.ready_queue:
            return False
        if (self.algorithm != edited.algorithm
                or len(edited.processors_list) > len(self.processors_list)):
            return True

        def running_ids(state):
            """Compara a composição de execução sem depender da identidade de cópias dos TCBs."""
            return {(task.id, task.instance_number) for task in state.running_tasks}

        if running_ids(self) != running_ids(edited):
            return True

        def priorities(state):
            """Obtém assinaturas da política para comparar valores antes e depois da edição."""
            values = {}
            policy = get_algorithm(state.algorithm)
            for task in state.ready_queue + state.running_tasks:
                values[(task.id, task.instance_number)] = policy.priority_signature(task)
            return values

        before = priorities(self)
        after = priorities(edited)
        # Remover somente uma tarefa que já estava esperando não altera quem
        # executa; admitir/retomar uma candidata ou mudar sua prioridade pode alterar.
        return any(key not in before or value != before[key] for key, value in after.items())

    def _edit_task(self, task_id, changes, task_state):
        """Valida atributos/estado, preserva trabalho executado e mantém filas e CPUs coerentes."""
        if task_id in self.removed_task_ids:
            raise ValueError("A tarefa foi removida. Retroceda a simulação para restaurá-la.")
        task, source = self.current_task(task_id)
        target = source
        if task_state is not None:
            target = next((name for name in TASK_STATES
                           if name.casefold() == str(task_state).strip().casefold()), None)
            if target is None:
                raise ValueError("Estado inválido. Escolha Nova, Pronta, Executando, Suspensa ou Finalizada.")
        values = validate_changes(task, changes)
        self._validate_unique_color(values['color'], task_id)
        if source == "Finalizada" and target != "Finalizada":
            raise ValueError("Uma instância finalizada não pode ser reaberta. Retroceda a simulação para editá-la antes do término.")
        if values["arrival"] != task.arrival and source != "Nova":
            raise ValueError("O ingresso dessa instância já ocorreu. Retroceda até o estado Nova para alterá-lo.")
        if target == "Nova":
            if task.computational_time:
                raise ValueError("Uma instância que já executou não pode voltar a Nova. Retroceda a simulação.")
            if values["arrival"] < self.tick:
                raise ValueError("Uma tarefa Nova precisa ter ingresso no instante atual ou no futuro.")
        elif values["arrival"] > self.tick:
            raise ValueError("A tarefa ainda não chegou. Antecipe o ingresso enquanto ela estiver Nova ou avance o relógio.")

        # Características se aplicam às instâncias ainda não concluídas. Ingressos
        # já registrados e dados dos intervalos executados não são reescritos.
        siblings = [other for name, queue in self.task_queues() if name not in ("Finalizada", "Removida")
                    for other in queue if other.id == task_id]
        if not siblings:
            siblings = [task]
        changed_fields = [key for key, value in values.items() if value != getattr(task, key)]
        if changed_fields or source != target:
            names = dict(color='cor', arrival='ingresso', duration='duração', period='período', deadline='prazo')
            details = []
            for key in changed_fields:
                if key == 'events':
                    details.append(f"eventos: {len(task.events)} → {len(values[key])}")
                else:
                    details.append(f"{names[key]}: {getattr(task, key)} → {values[key]}")
            detail = ", ".join(details)
            if source != target:
                detail = (detail + "; " if detail else "") + f"{source} → {target}"
            self.result.system_events.append(SystemEvent(self.tick, f"Tarefa {task_id}: {detail}"))
        for other in siblings:
            finishing = other is task and target == "Finalizada"
            if (values["duration"] < other.computational_time
                    or (values["duration"] == other.computational_time and not finishing)):
                raise ValueError(f"A duração deve superar os {other.computational_time} ticks já executados pela instância {other.instance_number}, ou ser igual ao finalizar a instância.")
        for other in siblings:
            for key in ("color", "duration", "period", "deadline", "events"):
                setattr(other, key, deepcopy(values[key]))
            if other is task:
                other.arrival = values["arrival"]
            elif other in self.tasks_to_arrival:
                other.arrival = values["arrival"] + (other.instance_number - task.instance_number) * values["period"]
            other.end_period = other.arrival + other.period
            other.absolute_deadline = other.arrival + other.deadline
        info = next(info for info in self.result.tasks if info.id == task_id)
        for key in TASK_FIELDS:
            setattr(info, key, deepcopy(values[key]))

        if source == target:
            return
        free_cpu = None
        if target == "Executando":
            free_cpu = next((cpu for cpu in self.processors_list if cpu.task_running is None), None)
            if free_cpu is None:
                raise ValueError("Todos os processadores estão ocupados. Libere um processador ou aumente a quantidade antes de colocar a tarefa em execução.")
        for _, queue in self.task_queues():
            if task in queue:
                queue.remove(task)
        if task.processor is not None:
            task.processor.task_running = None
            task.processor = None

        if target == "Nova":
            # Desfaz uma admissão manual no próprio instante atual, sem tocar nos
            # intervalos anteriores e sem duplicar a chegada no próximo passo.
            self.result.events = [event for event in self.result.events
                                  if not (event.kind == "arrival" and event.tick == self.tick
                                          and event.task_id == task.id
                                          and event.instance == task.instance_number)]

        if target != "Nova":
            if not any(event.kind == "arrival" and event.task_id == task.id
                       and event.instance == task.instance_number for event in self.result.events):
                self.result.events.append(Event("arrival", self.tick, task.id, task.instance_number))
            self.enqueue_next_instance(task)
        queues = dict(self.task_queues())
        queues[target].append(task)
        if target == "Executando":
            task.processor = free_cpu
            free_cpu.task_running = task
        elif target == "Finalizada":
            self.result.events.append(Event("finish", self.tick, task.id, task.instance_number))

    def _validate_unique_color(self, color, task_id):
        """Impede confusão com outra tarefa, inclusive em intervalos já desenhados."""
        current_conflict = any(info.id != task_id and info.color.upper() == color.upper()
                               for info in self.result.tasks)
        past_conflict = any(index != task_id and previous.upper() == color.upper()
                            for colors in self.result.task_colors for index, previous in colors.items())
        if current_conflict or past_conflict:
            raise ValueError(f"A cor {color} já é usada por outra tarefa. Cada tarefa precisa de uma cor diferente.")

    def _add_task(self, fields):
        """Inclui uma definição periódica no instante atual, sem reescrever o passado."""
        task_id = positive_integer(fields.get('id', ''), 'Identificador')
        if any(key not in ('id',) + TASK_FIELDS for key in fields):
            raise ValueError("A inclusão contém um campo de tarefa desconhecido.")
        if any(info.id == task_id for info in self.result.tasks):
            raise ValueError("Este identificador já pertence ao histórico. Escolha um novo ID.")
        defaults = dict(color='000001', arrival=self.tick, duration=1, period=4, deadline=4, events=[])
        defaults.update({key: value for key, value in fields.items() if key in TASK_FIELDS})
        values = validate_changes(SimpleNamespace(**defaults), {})
        if values['arrival'] < self.tick:
            raise ValueError("O ingresso de uma nova tarefa não pode estar no passado.")
        self._validate_unique_color(values['color'], task_id)
        task = TCB([str(task_id)] + [str(values[key]) for key in TASK_FIELDS[:-1]] + [repr(values['events'])])
        self.tasks_to_arrival.append(task)
        self.result.tasks.append(TaskInfo(task))
        self.result.system_events.append(SystemEvent(self.tick, f"Tarefa {task_id} incluída; ingresso {task.arrival}"))
        return task

    def _remove_task(self, task_id):
        """Cancela todas as instâncias restantes da definição, preservando as concluídas."""
        if task_id in self.removed_task_ids or not any(info.id == task_id for info in self.result.tasks):
            raise ValueError("Selecione uma tarefa existente que ainda não foi removida.")
        count = 0
        for name, queue in self.task_queues():
            if name in ('Finalizada', 'Removida'):
                continue
            for task in tuple(queue):
                if task.id == task_id:
                    queue.remove(task)
                    if task.processor is not None:
                        task.processor.task_running = None
                        task.processor = None
                    self.removed_tasks.append(task)
                    count += 1
        self.removed_task_ids.add(task_id)
        next(info for info in self.result.tasks if info.id == task_id).removed_tick = self.tick
        self.result.events.append(Event('remove', self.tick, task_id, 0))
        self.result.system_events.append(SystemEvent(self.tick, f"Tarefa {task_id} removida; {count} instância(s) cancelada(s)"))


def positive_integer(value, name, minimum=1):
    """Converte um campo numérico e informa sua unidade/limite na mensagem de erro."""
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError(f"{name} deve ser um número inteiro.") from None
    if number < minimum:
        raise ValueError(f"{name} deve ser maior ou igual a {minimum}.")
    return number


def validate_changes(task, changes):
    """Normaliza atributos de tarefas sem impor igualdade entre prazo e período."""
    if any(key not in TASK_FIELDS for key in changes):
        raise ValueError("A edição contém um campo de tarefa desconhecido.")
    values = {key: deepcopy(changes.get(key, getattr(task, key))) for key in TASK_FIELDS}
    values["color"] = str(values["color"]).strip().removeprefix("#").upper()
    if not re.fullmatch(r"[0-9A-F]{6}", values["color"]):
        raise ValueError("Cor inválida. Use seis dígitos RGB hexadecimais, por exemplo FF0000.")
    for key, label in (("arrival", "Ingresso"), ("duration", "Duração"),
                       ("period", "Período"), ("deadline", "Prazo")):
        values[key] = positive_integer(values[key], label, 0 if key == "arrival" else 1)
    if isinstance(values["events"], str):
        try:
            values["events"] = ast.literal_eval(values["events"].strip() or "[]")
        except (ValueError, SyntaxError):
            raise ValueError("Eventos devem ser uma lista de textos, por exemplo ['evento1'].") from None
    if not isinstance(values["events"], list) or any(not isinstance(item, str) for item in values["events"]):
        raise ValueError("Eventos devem ser uma lista de textos, por exemplo ['evento1'].")
    return values
