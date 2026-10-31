"""Estruturas de apresentação; o histórico de intervalos não depende da janela."""
# Projeto A, requisito 4.4: cada definição periódica libera dez instâncias.
SIMULATION_LIMIT = 10


class Event:
    """Evento de uma instância; o tick é o instante exato, não o índice do desenho."""
    def __init__(self, kind, tick, task_id, instance):
        """Inicializa os dados de Event com vínculos e valores próprios deste objeto."""
        self.kind = kind
        self.tick = tick
        self.task_id = task_id
        self.instance = instance


class TaskInfo:
    """Metadados para apresentação, preservados mesmo após remover a tarefa."""
    def __init__(self, task):
        """Inicializa os dados de TaskInfo com vínculos e valores próprios deste objeto."""
        self.id = task.id
        # Identidade da definição no histórico, independente do ID editável.
        self.key = task.id
        self.color = task.color
        self.arrival = task.arrival
        self.duration = task.duration
        self.period = task.period
        self.deadline = task.deadline
        self.events = list(task.events)
        self.removed_tick = None


class SystemEvent:
    """Reconfiguração feita no instante atual, identificada no gráfico por S#."""
    def __init__(self, tick, description):
        """Inicializa os dados de SystemEvent com vínculos e valores próprios deste objeto."""
        self.tick = tick
        self.description = description


# Os dados de cada intervalo são preservados mesmo após uma edição do sistema.
class SimulationResult:
    """Dados de apresentação por intervalo; edições atuais não reescrevem o passado."""
    def __init__(self, algorithm, num_cpus, tasks):
        """Inicializa os dados de SimulationResult com vínculos e valores próprios deste objeto."""
        self.algorithm = algorithm
        self.initial_algorithm = algorithm
        self.initial_num_cpus = num_cpus
        self.num_cpus = num_cpus
        self.tasks = tasks
        # IDs usados por uma família ficam reservados a ela. Os registros de
        # execução conservam o ID original; o desenho resolve seu nome atual.
        self.task_aliases = {info.id: info.id for info in tasks}
        self.total_ticks = 0
        # Cada linha contém somente as CPUs que existiam naquele tick.
        self.timeline = []
        self.events = []
        self.suspended_timeline = []
        self.current_suspended = []
        self.task_colors = []
        self.system_events = []

    def resolve_task_id(self, task_id):
        """Associa um ID histórico ao ID atual sem reescrever ticks ou eventos."""
        return self.task_aliases.get(task_id, task_id)

    def task_key(self, task_id):
        """Obtém a identidade estável para comparar retratos antes/depois de renomear."""
        current_id = self.resolve_task_id(task_id)
        return next(info.key for info in self.tasks if info.id == current_id)

    @property
    def max_cpus(self):
        """Mantém visíveis CPUs históricas mesmo depois de reduzir o sistema atual."""
        return max([self.num_cpus] + [len(row) for row in self.timeline])
