"""Relógio em ticks, liberações periódicas e aplicação de decisões por eventos."""
from utils import initialize_processors, pair_cpus_tasks
from extract_config import extract_system_parameters, extract_task_list
from choose_task import choose_task, draws, get_algorithm, normalize_algorithm
from copy import deepcopy
import random

from simulation_state import simulation_state, positive_integer, validate_changes
from simulation_result import Event, TaskInfo, SimulationResult, SIMULATION_LIMIT


# state_list[t] guarda o estado no instante t; o último é o estado atual.
state_list = []

# Lê o arquivo de configuração e confere se o sistema é válido.
# Em caso de erro, imprime o motivo e chama exit(1) (como nas outras funções de leitura).
def load_system(file_path):
    """Carrega entradas validadas; o núcleo não impõe restrições temporais além do formato."""
    algorithm, quantum, num_cpus = extract_system_parameters(file_path)
    task_list = extract_task_list(file_path)

    print(f"algorithm {algorithm}")
    print(f"quantum {quantum}")
    print(f"num_cpus {num_cpus}")

    return algorithm, quantum, num_cpus, task_list


# Inicia um histórico novo, sem alterar as tarefas recebidas.
def start_simulation(algorithm, num_cpus, task_list):
    """Inicia um histórico independente com TCBs copiados e uma CPU por identificador."""
    algorithm = normalize_algorithm(algorithm)
    num_cpus = positive_integer(num_cpus, 'Número de processadores')
    tasks = deepcopy(task_list)
    ids, colors = set(), set()
    for task in tasks:
        for field, value in validate_changes(task, {}).items():
            setattr(task, field, value)
        if task.id in ids or task.color in colors:
            raise ValueError('Identificadores e cores precisam ser exclusivos por tarefa.')
        if task.period <= 0 or task.deadline <= 0 or task.duration <= 0 or task.arrival < 0 or task.id <= 0:
            raise ValueError('A definição periódica contém um tempo ou identificador inválido.')
        ids.add(task.id)
        colors.add(task.color)
    result = SimulationResult(algorithm, num_cpus, [TaskInfo(task) for task in tasks])
    initial_state = simulation_state(
        algorithm=algorithm,
        processors_list=initialize_processors(num_cpus),
        tasks_to_arrival=tasks,
        result=result,
    )
    # Preserva a referência da lista compartilhada com a interface.
    state_list.clear()
    state_list.append(initial_state)
    return initial_state


# Executa a mesma transição usada pelo modo passo a passo.
def run_simulation(algorithm, num_cpus, task_list):
    """Reutiliza as transições do debugger até concluir todas as instâncias."""
    current_state = start_simulation(algorithm, num_cpus, task_list)
    while not current_state.is_finished:
        current_state = scale(current_state)
        state_list.append(current_state)
    return current_state.result


def _schedule(state):
    """Escolhe as instâncias executáveis e aplica somente as trocas necessárias."""
    print(f"A specific event triggered the scheduler in tick {state.tick}.")
    ready_queue = state.ready_queue
    running_tasks = state.running_tasks
    previously_running = tuple(running_tasks)
    candidates = ready_queue + running_tasks
    selected = []
    rng = random.Random()
    rng.setstate(state.random_state)
    draws.clear()

    for _ in range(min(len(state.processors_list), len(candidates))):
        chosen = choose_task(candidates, state.algorithm, rng, state)
        candidates.remove(chosen)
        selected.append(chosen)

    selected_set = set(selected)
    for winner, loser in draws:
        if winner in selected_set and loser not in selected_set and winner not in previously_running:
            state.result.events.append(Event("draw", state.tick, winner.id, winner.instance_number))
    state.random_state = rng.getstate()

    # Mesmo após uma chegada, a seleção pode continuar igual. Nesse caso não
    # reconstruímos/reordenamos as filas nem refazemos a associação com as CPUs.
    if selected_set == set(previously_running):
        return
    for task in previously_running:
        if task not in selected_set:
            running_tasks.remove(task)
            ready_queue.append(task)
            task.processor.task_running = None
            task.processor = None
    for task in selected:
        if task not in previously_running:
            ready_queue.remove(task)
            running_tasks.append(task)
    pair_cpus_tasks(running_tasks, state.processors_list)


# Constrói o próximo estado sem modificar o estado recebido nem o histórico.
def scale(current_state):
    """Processa eventos e executa um intervalo, preservando o estado recebido."""
    if current_state.is_finished:
        return current_state

    # Uma única cópia preserva os vínculos entre tarefas, filas e processadores,
    # inclusive as referências circulares tarefa.processor / cpu.task_running.
    current_state = deepcopy(current_state)
    result = current_state.result

    tick = current_state.tick
    tasks_to_arrival = current_state.tasks_to_arrival
    ready_queue = current_state.ready_queue
    running_tasks = current_state.running_tasks
    terminated_tasks = current_state.terminated_tasks
    processors_list = current_state.processors_list

    print(f"==================== TICK: {tick} ===================")

    # O calendário libera instâncias por período, mesmo se a antecessora ainda
    # executa. A sucessora é agendada na admissão, nunca no término ou no prazo.
    while True:
        arrived = [task for task in tasks_to_arrival if task.arrival <= tick]
        if not arrived:
            break
        for task in arrived:
            tasks_to_arrival.remove(task)
            if task.release_state == 'Suspensa':
                current_state.suspended_tasks.append(task)
            else:
                ready_queue.append(task)
                current_state.reschedule_needed = True
            result.events.append(Event("arrival", tick, task.id, task.instance_number))
            current_state.enqueue_next_instance(task)
            print(f"Task {task.id}({task.instance_number}) has arrived at tick {tick}.")

    # O prazo é independente do período. Atraso é um evento, não uma conclusão.
    active_tasks = ready_queue + running_tasks + current_state.suspended_tasks

    for task in active_tasks:
        # Uma edição pode aproximar o prazo de uma instância já admitida.
        if task.absolute_deadline <= tick and not task.is_late:
            print(f"SCHEADULING ERROR: Task {task.id}({task.instance_number}) has not completed its execution within its deadline at tick {tick}.")
            result.events.append(Event("deadline_miss", tick, task.id, task.instance_number))
            task.is_late = True

    # Req. 1.1: verificar eventos a cada tick; RM/EDF só precisam de uma nova
    # decisão quando há admissão, liberação de CPU ou uma edição relevante.
    # Conclusões em t e chegadas em t são reunidas antes de executar [t, t+1).
    policy = get_algorithm(current_state.algorithm)
    # Políticas futuras podem registrar evento de quantum. RM/EDF não possuem
    # esse callback e não são reavaliados por simples passagem do relógio.
    if policy.tick_event is not None and policy.tick_event(current_state):
        current_state.reschedule_needed = True
    if current_state.reschedule_needed:
        current_state.reschedule_needed = False
        if ready_queue:
            _schedule(current_state)

    tick_row = []   # o que cada CPU fez neste tick

    for cpu in processors_list:
        if cpu.task_running == None:
            tick_row.append(None)
            print(f"Processor: {cpu.id}: No task is running at tick {tick} -> {tick + 1}.")
            continue

        task = cpu.task_running
        tick_row.append((task.id, task.instance_number))
        print(f"Processor {cpu.id}: Task {task.id}({task.instance_number}) is running at tick {tick} -> {tick + 1}.")
        task.computational_time += 1

        if task.computational_time >= task.duration:
            result.events.append(Event("finish", tick + 1, task.id, task.instance_number))
            task.processor = None
            cpu.task_running = None
            running_tasks.remove(task)
            terminated_tasks.append(task)
            if ready_queue:
                current_state.reschedule_needed = True
            if task.instance_number == SIMULATION_LIMIT:
                print(f"Task {task.id}({task.instance_number}) has executed {SIMULATION_LIMIT} times and has reached the simulation limit at tick {tick} -> {tick + 1}.")

    result.timeline.append(tick_row)
    result.suspended_timeline.append([(task.id, task.instance_number)
                                      for task in current_state.suspended_tasks])
    result.task_colors.append({info.id: info.color for info in result.tasks})
    current_state.tick = tick + 1
    current_state.tasks_to_arrival = tasks_to_arrival
    current_state.ready_queue = ready_queue
    current_state.running_tasks = running_tasks
    current_state.terminated_tasks = terminated_tasks
    result.total_ticks = current_state.tick
    current_state.refresh_result()
    return current_state
