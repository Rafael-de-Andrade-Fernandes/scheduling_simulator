from choose_task import choose_task, draws
from utils import pair_cpus_tasks
from simulation_state import Event, SIMULATION_LIMIT


# Simula UM tick de relógio: o que acontece entre o instante "tick" e "tick + 1".
# A função altera o state recebido (quem chama deve passar uma cópia se quiser guardar o anterior).
def advance_one_tick(state):
    tick = state.tick
    num_cpus = state.num_cpus

    # Copiamos os campos do state para variáveis locais (mais curtas de ler)
    tasks_to_arrival = state.tasks_to_arrival
    ready_queue = state.ready_queue
    running_tasks = state.running_tasks
    terminated_tasks = state.terminated_tasks
    processors_list = state.processors_list

    state.log.append(f"==================== TICK: {tick} ===================")

    # timeout verify
    active_tasks = ready_queue + running_tasks

    for task in active_tasks:
        # só avisa uma vez por instância (se o prazo for editado depois do atraso, não repete)
        if task.absolute_deadline == tick and not task.is_late:
            state.log.append(f"SCHEADULING ERROR: Task {task.id}({task.instance_number}) has not completed its execution within its deadline at tick {tick}.")
            state.events.append(Event("deadline_miss", tick, task.id, task.instance_number))
            task.is_late = True
            if task.instance_number < SIMULATION_LIMIT:
                new_instance = task.create_next_instance()
                tasks_to_arrival.append(new_instance)

    # arrival of tasks

    still_to_arrival = []

    for task in tasks_to_arrival:
        if task.arrival <= tick:
            ready_queue.append(task)
            state.events.append(Event("arrival", tick, task.id, task.instance_number))
            state.log.append(f"Task {task.id}({task.instance_number}) has arrived at tick {tick}.")
        else:
            still_to_arrival.append(task)

    tasks_to_arrival = still_to_arrival

    # choose the num_cpus most prioritized tasks:
    candidates = ready_queue + running_tasks
    previously_running = running_tasks
    running_tasks = []
    draws.clear()

    for i in range(num_cpus):
        task_chosen = choose_task(candidates, state.algorithm)
        if task_chosen:
            candidates.remove(task_chosen)
            running_tasks.append(task_chosen)

    # sorteio só aparece no gráfico se a vencedora foi escolhida,
    # a perdedora ficou de fora e a vencedora estava (re)começando a executar
    for winner, loser in draws:
        if winner in running_tasks and loser not in running_tasks and winner not in previously_running:
            state.events.append(Event("draw", tick, winner.id, winner.instance_number))

    # no chosen tasks go back to to ready_queue:
    ready_queue = candidates
    for task in ready_queue:
        task.processor = None

    # colocar as running_tasks nos processadores corretos:
    running_tasks, processors_list = pair_cpus_tasks(running_tasks, processors_list)

    tick_row = []   # o que cada CPU fez neste tick

    for cpu in processors_list:
        if cpu.task_running == None:
            tick_row.append(None)
            state.log.append(f"Processor: {cpu.id}: No task is running at tick {tick} -> {tick + 1}.")
            continue

        task = cpu.task_running
        tick_row.append((task.id, task.instance_number))
        state.log.append(f"Processor {cpu.id}: Task {task.id}({task.instance_number}) is running at tick {tick} -> {tick + 1}.")
        task.computational_time += 1

        if task.computational_time >= task.duration:
            state.events.append(Event("finish", tick + 1, task.id, task.instance_number))
            task.processor = None
            cpu.task_running = None
            running_tasks.remove(task)
            if task.instance_number == SIMULATION_LIMIT:
                terminated_tasks.append(task)
                state.log.append(f"Task {task.id}({task.instance_number}) has executed {SIMULATION_LIMIT} times and has reached the simulation limit at tick {tick} -> {tick + 1}.")
            elif task.is_late == False:
                new_instance = task.create_next_instance()
                tasks_to_arrival.append(new_instance)
                state.log.append(f"Task {task.id}({task.instance_number}) completed his computation_time at tick {tick} -> {tick + 1}. Enqueuing new instance to arrive at tick {new_instance.arrival}.")

    # Guardamos de volta no state tudo o que mudou
    state.tasks_to_arrival = tasks_to_arrival
    state.ready_queue = ready_queue
    state.running_tasks = running_tasks
    state.processors_list = processors_list
    state.timeline.append(tick_row)
    state.tick = tick + 1

    if state.is_finished():
        state.log.append(f"End of simulation at tick {state.tick}. All tasks have reached the simulation limit of {SIMULATION_LIMIT} executions.")
