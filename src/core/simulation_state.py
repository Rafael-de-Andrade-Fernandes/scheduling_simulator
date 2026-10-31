from utils import initialize_processors

# Cada tarefa periódica termina depois de executar este número de vezes (item 4.4 do PDF)
SIMULATION_LIMIT = 10


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


# Tudo o que muda durante a simulação fica dentro desta struct.
# Uma cópia completa dela (copy.deepcopy) é uma "foto" do sistema em um tick;
# é assim que o simulador consegue avançar e retroceder.
class SimulationState:
    def __init__(self, algorithm, num_cpus, task_list):
        self.algorithm = algorithm
        self.num_cpus = num_cpus
        self.tick = 0                       # relógio global: quantos ticks já foram simulados
        self.total_tasks = len(task_list)
        self.task_ids = sorted([task.id for task in task_list])

        self.tasks_to_arrival = list(task_list)
        self.ready_queue = []
        self.running_tasks = []
        self.terminated_tasks = []
        self.processors_list = initialize_processors(num_cpus)

        # Registros usados pela parte gráfica
        # timeline[tick][cpu] = None (CPU desligada) ou (id_da_tarefa, instancia)
        self.timeline = []
        self.events = []            # lista de Event
        self.log = []               # mensagens da simulação, uma por linha
        self.warnings = []          # avisos da leitura do arquivo (ex: tarefa aperiódica ignorada)

    # A simulação termina quando todas as tarefas chegaram ao limite de execuções
    def is_finished(self):
        finished_ids = set()
        for task in self.terminated_tasks:
            finished_ids.add(task.id)
        return len(finished_ids) == self.total_tasks

    # Todas as instâncias vivas de uma tarefa (aguardando chegada, prontas ou executando)
    def instances_of(self, task_id):
        found = []
        for task in self.tasks_to_arrival + self.ready_queue + self.running_tasks:
            if task.id == task_id:
                found.append(task)
        return found

    # Devolve (instancia, situacao) da tarefa. situacao pode ser:
    # "running", "ready", "waiting" (ainda não chegou), "finished" ou "none"
    def current_instance(self, task_id):
        for task in self.running_tasks:
            if task.id == task_id:
                return task, "running"
        for task in self.ready_queue:
            if task.id == task_id:
                return task, "ready"

        # a próxima a chegar é a que tem o menor instante de chegada
        waiting = None
        for task in self.tasks_to_arrival:
            if task.id == task_id and (waiting is None or task.arrival < waiting.arrival):
                waiting = task
        if waiting is not None:
            return waiting, "waiting"

        for task in self.terminated_tasks:
            if task.id == task_id:
                return task, "finished"
        return None, "none"
