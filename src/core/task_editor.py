import re

from choose_task import SCHEDULERS
from utils import initialize_processors


# Converte um texto em número inteiro maior que zero (ou maior ou igual, se allow_zero).
# Devolve (valor, "") se deu certo, ou (None, mensagem_de_erro) se não deu.
def parse_int(text, field_name, allow_zero):
    try:
        value = int(text.strip())
    except ValueError:
        return None, f"{field_name} deve ser um número inteiro."
    if value < 0 or (value == 0 and not allow_zero):
        if allow_zero:
            return None, f"{field_name} não pode ser negativo."
        return None, f"{field_name} deve ser maior que zero."
    return value, ""


# Modifica as características e o estado de uma tarefa no tick atual.
# values é um dicionário de textos, com as chaves: color, arrival, duration,
# period, deadline, executed (ticks já executados da instância atual).
# Devolve (True, mensagem) se aplicou, ou (False, motivo) se a mudança é inválida.
# Nada é alterado se qualquer campo for recusado.
def edit_task(state, task_id, values):
    instances = state.instances_of(task_id)
    if len(instances) == 0:
        return False, f"A tarefa {task_id} já terminou: não há o que modificar."

    current, where = state.current_instance(task_id)
    is_active = (where == "running" or where == "ready")

    # 1. Lê os campos e confere se são números/cores válidos
    new_color = values["color"].strip().upper()
    if not re.match(r'^[0-9A-F]{6}$', new_color):
        return False, "Cor inválida: use 6 dígitos hexadecimais (ex: 00FF00)."

    numbers = {}
    for key, name, allow_zero in [("arrival", "Ingresso", True), ("duration", "Duração", False),
                                  ("period", "Período", False), ("deadline", "Prazo", False),
                                  ("executed", "Já executado", True)]:
        number, message = parse_int(values[key], name, allow_zero)
        if number is None:
            return False, message
        numbers[key] = number

    new_arrival = numbers["arrival"]
    new_duration = numbers["duration"]
    new_period = numbers["period"]
    new_deadline = numbers["deadline"]
    new_executed = numbers["executed"]

    # 2. Regras do sistema simulado
    if new_period != new_deadline:
        return False, "RM e EDF exigem prazo igual ao período."

    if new_arrival != current.arrival:
        if where != "waiting" or current.instance_number != 1:
            return False, ("O ingresso só pode mudar antes de a tarefa chegar. "
                           "O ingresso das instâncias seguintes é definido pelo período.")
        if new_arrival < state.tick:
            return False, f"O ingresso não pode ser anterior ao tick atual ({state.tick})."

    old_executed = current.computational_time if is_active else 0
    if new_executed != old_executed and not is_active:
        return False, "A tarefa ainda não chegou: não há tempo executado para modificar."

    # O tempo já executado de cada instância que chegou precisa ser menor que a duração
    for task in instances:
        if task not in state.ready_queue and task not in state.running_tasks:
            continue
        task_executed = new_executed if task is current else task.computational_time
        if task_executed >= new_duration:
            if task is current and new_executed != old_executed:
                return False, f"Já executado ({new_executed}) deve ser menor que a duração ({new_duration})."
            return False, (f"Duração inválida: a instância {task.instance_number} já executou "
                           f"{task_executed} ticks e a duração precisa ser maior que isso.")

    # 3. Confere se os novos prazos e chegadas ainda estão no futuro
    for task in instances:
        waiting = task in state.tasks_to_arrival
        if waiting and task.instance_number > 1:
            shifted_arrival = task.arrival - task.period + new_period
            if shifted_arrival < state.tick:
                return False, (f"Período inválido: a instância {task.instance_number} "
                               f"passaria a chegar no tick {shifted_arrival}, que já passou.")
        if not waiting:
            if task.arrival + new_deadline < state.tick:
                return False, (f"Prazo inválido: o prazo da instância {task.instance_number} "
                               "terminaria antes do tick atual.")

    # 4. Tudo certo: aplica as mudanças em todas as instâncias vivas da tarefa
    for task in instances:
        waiting = task in state.tasks_to_arrival
        if waiting and task.instance_number > 1:
            task.arrival = task.arrival - task.period + new_period
        if waiting and task.instance_number == 1 and task is current:
            task.arrival = new_arrival

        task.color = new_color
        task.duration = new_duration
        task.period = new_period
        task.deadline = new_deadline
        task.end_period = task.arrival + task.period
        task.absolute_deadline = task.arrival + task.deadline

    if is_active:
        current.computational_time = new_executed

    state.log.append(f"Task {task_id} was modified by the user at tick {state.tick}.")
    return True, f"Tarefa {task_id} modificada a partir do tick {state.tick}."


# Troca o algoritmo de escalonamento; vale a partir do próximo tick.
def set_algorithm(state, name):
    name = name.strip().upper()
    if name not in SCHEDULERS:
        return False, f"Algoritmo desconhecido. Disponíveis: {', '.join(sorted(SCHEDULERS.keys()))}."
    state.algorithm = name
    state.log.append(f"Scheduling algorithm changed to {name} at tick {state.tick}.")
    return True, f"Algoritmo {name} será usado a partir do tick {state.tick}."


# Troca a quantidade de processadores. Só é possível antes do primeiro tick:
# depois disso o gráfico já tem CPUs com histórico e não dá para recalculá-lo.
def set_num_cpus(state, num_cpus):
    if num_cpus < 1:
        return False, "A quantidade de processadores deve ser pelo menos 1."
    if state.tick != 0:
        return False, ("Não é possível mudar a quantidade de processadores durante a simulação, "
                       "porque os ticks já simulados usaram a quantidade anterior. "
                       "Volte ao tick 0 ou inicie uma nova simulação.")
    state.num_cpus = num_cpus
    state.processors_list = initialize_processors(num_cpus)
    return True, f"Quantidade de processadores alterada para {num_cpus}."
