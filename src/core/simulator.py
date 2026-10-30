from utils import initialize_processors, pair_cpus_tasks
from extract_config import extract_system_parameters, extract_task_list
from choose_task import choose_task, draws

# Cada tarefa periódica termina depois de executar este número de vezes
SIMULATION_LIMIT = 3


# Um evento importante da simulação (vai virar um desenho no gráfico de Gantt).
# kind pode ser:
#   "arrival"       -> chegada de uma instância da tarefa
#   "finish"        -> término da execução de uma instância
#   "deadline_miss" -> perda de prazo
#   "draw"          -> sorteio no desempate
class Event:
    def __init__(self, kind, tick, task_id, instance):
        self.kind = kind
        self.tick = tick
        self.task_id = task_id
        self.instance = instance


# Características de uma tarefa, como vieram do arquivo de configuração.
class TaskInfo:
    def __init__(self, task):
        self.id = task.id
        self.color = task.color
        self.arrival = task.arrival
        self.duration = task.duration
        self.period = task.period
        self.deadline = task.deadline
        self.events = list(task.events)


# Tudo o que a parte gráfica precisa saber depois da simulação.
# É como uma struct em C: só guarda dados, não tem lógica.
class SimulationResult:
    def __init__(self, algorithm, num_cpus, tasks):
        self.algorithm = algorithm
        self.num_cpus = num_cpus
        self.tasks = tasks          # lista de TaskInfo
        self.total_ticks = 0
        # timeline[tick][cpu] = None (CPU desligada) ou (id_da_tarefa, instancia)
        self.timeline = []
        self.events = []            # lista de Event


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


# Executa a simulação completa e devolve um SimulationResult.
def run_simulation(algorithm, num_cpus, task_list):
    tasks_info = []
    for task in task_list:
        tasks_info.append(TaskInfo(task))
    result = SimulationResult(algorithm, num_cpus, tasks_info)

    # INITIALIZE SIMULATION VARIABLES

    tick = 0

    tasks_to_arrival = list(task_list)
    ready_queue = []
    running_tasks = []
    terminated_tasks = []

    processors_list = initialize_processors(num_cpus)

    # MAIN SCHEDULING SIMULATION LOOP

    while len(terminated_tasks) != len(task_list):

        print(f"==================== TICK: {tick} ===================")

        # timeout verify
        active_tasks = ready_queue + running_tasks

        for task in active_tasks:
            if task.absolute_deadline == tick:
                print(f"SCHEADULING ERROR: Task {task.id}({task.instance_number}) has not completed its execution within its deadline at tick {tick}.")
                result.events.append(Event("deadline_miss", tick, task.id, task.instance_number))
                task.is_late = True
                if task.instance_number < SIMULATION_LIMIT:
                    new_instance = task.create_next_instance()
                    tasks_to_arrival.append(new_instance)

        # arrival of tasks

        still_to_arrival = []

        for task in tasks_to_arrival:
            if task.arrival <= tick:
                ready_queue.append(task)
                result.events.append(Event("arrival", tick, task.id, task.instance_number))
                print(f"Task {task.id}({task.instance_number}) has arrived at tick {tick}.")
            else:
                still_to_arrival.append(task)

        tasks_to_arrival = still_to_arrival

        # choose the num_cpus most prioritized tasks:
        candidates = ready_queue + running_tasks
        previously_running = running_tasks
        running_tasks = []
        draws.clear()

        for i in range(num_cpus):
            task_chosen = choose_task(candidates, algorithm)
            if task_chosen:
                candidates.remove(task_chosen)
                running_tasks.append(task_chosen)

        # sorteio só aparece no gráfico se a vencedora foi escolhida,
        # a perdedora ficou de fora e a vencedora estava (re)começando a executar
        for winner, loser in draws:
            if winner in running_tasks and loser not in running_tasks and winner not in previously_running:
                result.events.append(Event("draw", tick, winner.id, winner.instance_number))

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
                print(f"Processor: {cpu.id}: No task is running at tick {tick} -> {tick + 1}.")
                continue

            task = cpu.task_running
            tick_row.append((task.id, task.instance_number))
            print(f"Processor {cpu.id}: Task {task.id}({task.instance_number}) is running at tick {tick} -> {tick + 1}.")
            task.computational_time += 1

            if task.computational_time == task.duration:
                result.events.append(Event("finish", tick + 1, task.id, task.instance_number))
                task.processor = None
                cpu.task_running = None
                running_tasks.remove(task)
                if task.instance_number == SIMULATION_LIMIT:
                    terminated_tasks.append(task)
                    print(f"Task {task.id}({task.instance_number}) has executed {SIMULATION_LIMIT} times and has reached the simulation limit at tick {tick} -> {tick + 1}.")
                elif task.is_late == False:
                    new_instance = task.create_next_instance()
                    tasks_to_arrival.append(new_instance)
                    print(f"Task {task.id}({task.instance_number}) completed his computation_time at tick {tick} -> {tick + 1}. Enqueuing new instance to arrive at tick {new_instance.arrival}.")

        result.timeline.append(tick_row)
        tick += 1

    result.total_ticks = tick
    print(f"End of simulation at tick {tick}. All tasks have reached the simulation limit of {SIMULATION_LIMIT} executions.")
    return result
