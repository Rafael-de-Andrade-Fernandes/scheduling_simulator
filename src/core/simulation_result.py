"""Estruturas de apresentação; o histórico de intervalos não depende da janela."""
# Projeto A, requisito 4.4: cada definição periódica libera dez instâncias.
SIMULATION_LIMIT = 10


class Event:
    """Ocorrência em um instante; instance=0 representa a definição, como na remoção."""
    def __init__(self, kind, tick, task_id, instance):
        self.kind = kind
        self.tick = tick
        self.task_id = task_id
        self.instance = instance


class TaskInfo:
    """Descrição da tarefa para o gráfico, inclusive depois da sua remoção."""
    def __init__(self, task):
        self.id = task.id
        self.color = task.color
        self.arrival = task.arrival
        self.duration = task.duration
        self.period = task.period
        self.deadline = task.deadline
        self.events = list(task.events)
        self.removed_tick = None


class SystemEvent:
    """Intervenção do usuário exibida como S# no gráfico."""
    def __init__(self, tick, description):
        self.tick = tick
        self.description = description


class SimulationResult:
    """Dados de saída consultados pelo Gantt, pelo resumo e pela exportação."""
    def __init__(self, algorithm, num_cpus, tasks):
        self.algorithm = algorithm
        self.initial_algorithm = algorithm
        self.initial_num_cpus = num_cpus
        self.num_cpus = num_cpus
        self.tasks = tasks
        self.total_ticks = 0
        # timeline[t][cpu] é (id, instância) ou None para CPU desligada.
        # Uma CPU ausente da linha ainda não existia (ou já foi removida).
        self.timeline = []
        self.events = []
        self.suspended_timeline = []
        self.current_suspended = []
        self.system_events = []

    @property
    def max_cpus(self):
        # Não esconder linhas de CPUs usadas antes de uma redução de quantidade.
        return max([self.num_cpus] + [len(row) for row in self.timeline])
