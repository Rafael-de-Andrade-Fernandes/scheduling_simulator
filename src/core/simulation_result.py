# Limite já usado pelo simulador; a edição não altera a quantidade de instâncias.
SIMULATION_LIMIT = 3


class Event:
    def __init__(self, kind, tick, task_id, instance):
        self.kind = kind
        self.tick = tick
        self.task_id = task_id
        self.instance = instance


class TaskInfo:
    def __init__(self, task):
        self.id = task.id
        self.color = task.color
        self.arrival = task.arrival
        self.duration = task.duration
        self.period = task.period
        self.deadline = task.deadline
        self.events = list(task.events)


# Os dados de cada intervalo são preservados mesmo após uma edição do sistema.
class SimulationResult:
    def __init__(self, algorithm, num_cpus, tasks):
        self.algorithm = algorithm
        self.num_cpus = num_cpus
        self.tasks = tasks
        self.total_ticks = 0
        # Cada linha contém somente as CPUs que existiam naquele tick.
        self.timeline = []
        self.events = []
        self.suspended_timeline = []
        self.current_suspended = []
        self.task_colors = []

    @property
    def max_cpus(self):
        return max([self.num_cpus] + [len(row) for row in self.timeline])
