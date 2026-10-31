from utils import initialize_processors, pair_cpus_tasks
from extract_config import extract_system_parameters, extract_task_list
from choose_task import choose_task, draws
from copy import deepcopy
import random

from simulation_state import simulation_state
from simulation_result import Event, TaskInfo, SimulationResult, SIMULATION_LIMIT


# state_list[t] guarda o estado no instante t; o último é o estado atual.
state_list = []

# Lê o arquivo de configuração e confere se o sistema é válido.
# Em caso de erro, imprime o motivo e chama exit(1) (como nas outras funções de leitura).
def load_system(file_path):
    algorithm, quantum, num_cpus = extract_system_parameters(file_path)
    task_list = extract_task_list(file_path)

    print(f"algorithm {algorithm}")
    print(f"quantum {quantum}")
    print(f"num_cpus {num_cpus}")

    for task in task_list:
        task.print()
        # RM e EDF só aceitam tarefas com prazo igual ao período (Di = Pi)
        if task.period != task.deadline:
            print(f"Task {task.id} has a period different from its deadline. This is not allowed in RM or EDF scheduling. Exiting simulation.")
            exit(1)

    return algorithm, quantum, num_cpus, task_list


# Inicia um histórico novo, sem alterar as tarefas recebidas.
def start_simulation(algorithm, num_cpus, task_list):
    tasks = deepcopy(task_list)
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
        chosen = choose_task(candidates, state.algorithm, rng)
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

    # timeout verify
    active_tasks = ready_queue + running_tasks + current_state.suspended_tasks

    for task in active_tasks:
        # Uma edição pode aproximar o prazo de uma instância já admitida.
        if task.absolute_deadline <= tick and not task.is_late:
            print(f"SCHEADULING ERROR: Task {task.id}({task.instance_number}) has not completed its execution within its deadline at tick {tick}.")
            result.events.append(Event("deadline_miss", tick, task.id, task.instance_number))
            task.is_late = True
            current_state.enqueue_next_instance(task)

    # arrival of tasks

    arrived = [task for task in tasks_to_arrival if task.arrival <= tick]
    for task in arrived:
        ready_queue.append(task)
        current_state.reschedule_needed = True
        result.events.append(Event("arrival", tick, task.id, task.instance_number))
        print(f"Task {task.id}({task.instance_number}) has arrived at tick {tick}.")
    if arrived:
        tasks_to_arrival[:] = [task for task in tasks_to_arrival if task.arrival > tick]

    # Req. 1.1: verificar eventos a cada tick; RM/EDF só precisam de uma nova
    # decisão quando há admissão, liberação de CPU ou uma edição relevante.
    # Conclusões em t e chegadas em t são reunidas antes de executar [t, t+1).
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
            elif task.is_late == False:
                new_instance = current_state.enqueue_next_instance(task)
                if new_instance is not None:
                    print(f"Task {task.id}({task.instance_number}) completed his computation_time at tick {tick} -> {tick + 1}. Enqueuing new instance to arrive at tick {new_instance.arrival}.")

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
