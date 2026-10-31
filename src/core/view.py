from simulation_state import SIMULATION_LIMIT
from choose_task import SCHEDULERS


# Situação de uma tarefa em um dado tick (o "debugger" mostra isto na tela).
class TaskStatus:
    def __init__(self, task_id):
        self.id = task_id
        self.color = "000000"
        self.situation = ""          # texto: "pronta", "executando na CPU 1", ...
        self.instance = 0            # número da instância atual
        self.arrival = 0
        self.duration = 0
        self.period = 0
        self.deadline = 0
        self.absolute_deadline = 0
        self.executed = 0            # quantos ticks a instância atual já executou
        self.is_late = False
        self.events = []
        # contadores desde o início da simulação
        self.arrivals = 0
        self.finishes = 0
        self.misses = 0
        self.ticks_executed = 0
        self.cpus_used = []


# Tudo o que a parte gráfica precisa saber sobre o estado atual da simulação.
# É uma cópia só para leitura: a parte gráfica nunca altera o state do core.
class SimulationResult:
    def __init__(self, state):
        self.algorithm = state.algorithm
        self.algorithms = sorted(SCHEDULERS.keys())     # algoritmos disponíveis
        self.num_cpus = state.num_cpus
        self.tick = state.tick                          # relógio global atual
        self.total_ticks = state.tick                   # quantidade de ticks já simulados
        self.finished = state.is_finished()
        self.timeline = state.timeline
        self.events = state.events
        self.log = state.log
        self.warnings = state.warnings
        self.tasks = []                                 # lista de TaskStatus, uma por tarefa

        # Filas do sistema, como pares simples (id, instancia)
        self.ready = [(t.id, t.instance_number) for t in state.ready_queue]
        self.waiting = [(t.id, t.instance_number, t.arrival) for t in state.tasks_to_arrival]
        self.terminated = [(t.id, t.instance_number) for t in state.terminated_tasks]


# Texto que descreve a situação de uma tarefa
def describe_situation(state, task, where):
    if where == "running":
        for cpu in state.processors_list:
            if cpu.task_running is task:
                return f"executando na CPU {cpu.id}"
        return "executando"
    if where == "ready":
        return "pronta (aguardando processador)"
    if where == "waiting":
        return f"aguardando chegada (tick {task.arrival})"
    return f"terminada (executou {SIMULATION_LIMIT} vezes)"


# Monta o TaskStatus de uma tarefa a partir do state
def build_task_status(state, task_id):
    status = TaskStatus(task_id)
    task, where = state.current_instance(task_id)

    if task is not None:
        status.color = task.color
        status.situation = describe_situation(state, task, where)
        status.instance = task.instance_number
        status.arrival = task.arrival
        status.duration = task.duration
        status.period = task.period
        status.deadline = task.deadline
        status.absolute_deadline = task.absolute_deadline
        status.is_late = task.is_late
        status.events = list(task.events)
        if where == "running" or where == "ready":
            status.executed = task.computational_time

    for event in state.events:
        if event.task_id != task_id:
            continue
        if event.kind == "arrival":
            status.arrivals += 1
        elif event.kind == "finish":
            status.finishes += 1
        elif event.kind == "deadline_miss":
            status.misses += 1

    for tick in range(state.tick):
        for cpu in range(state.num_cpus):
            running = state.timeline[tick][cpu]
            if running is not None and running[0] == task_id:
                status.ticks_executed += 1
                if (cpu + 1) not in status.cpus_used:
                    status.cpus_used.append(cpu + 1)

    return status


# Monta a visão completa do state atual
def build_view(state):
    result = SimulationResult(state)
    for task_id in state.task_ids:
        result.tasks.append(build_task_status(state, task_id))
    return result
