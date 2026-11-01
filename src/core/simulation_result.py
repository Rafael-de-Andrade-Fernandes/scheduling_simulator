"""Estruturas de apresentação; o histórico de intervalos não depende da janela."""
# Projeto A, requisito 4.4: cada definição periódica libera dez instâncias.
SIMULATION_LIMIT = 10


# Evento de uma instância; o tick é o instante exato, não o índice do desenho.
class Event:
    def __init__(self, kind, tick, task_id, instance):
        self.kind = kind
        self.tick = tick
        self.task_id = task_id
        self.instance = instance


# Metadados para apresentação, preservados mesmo após remover a tarefa.
class TaskInfo:
    def __init__(self, task):
        self.id = task.id
        self.color = task.color
        self.arrival = task.arrival
        self.duration = task.duration
        self.period = task.period
        self.deadline = task.deadline
        self.events = list(task.events)
        self.removed_tick = None


# Reconfiguração feita no instante atual, identificada no gráfico por S#.
class SystemEvent:
    def __init__(self, tick, description):
        self.tick = tick
        self.description = description


# Os dados de cada intervalo são preservados mesmo após uma edição do sistema.
class SimulationResult:
    def __init__(self, algorithm, num_cpus, tasks):
        self.algorithm = algorithm
        self.initial_algorithm = algorithm
        self.initial_num_cpus = num_cpus
        self.num_cpus = num_cpus
        self.tasks = tasks
        self.total_ticks = 0
        # Cada linha contém somente as CPUs que existiam naquele tick.
        self.timeline = []
        self.events = []
        self.suspended_timeline = []
        self.current_suspended = []
        self.system_events = []

    # Mantém visíveis CPUs históricas mesmo depois de reduzir o sistema atual.
    @property
    def max_cpus(self):
        return max([self.num_cpus] + [len(row) for row in self.timeline])
