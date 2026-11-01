"""Bloco de controle por instância, separado de processadores e renderização."""
import ast

# Os mesmos nomes identificam o estado no núcleo e na interface.
NEW = "Nova"                # ainda não chegou
READY = "Pronta"            # chegou e espera por uma CPU
RUNNING = "Executando"      # está em uma CPU
SUSPENDED = "Suspensa"      # chegou, mas foi suspensa manualmente
FINISHED = "Finalizada"     # concluiu ou foi encerrada manualmente
REMOVED = "Removida"        # foi removida pelo usuário


class TCB:
    """Uma ocorrência da tarefa; outras ocorrências têm progresso e prazo próprios."""
    def __init__(self, task_line):
        fields = [field.strip() for field in task_line]

        self.id = int(fields[0])
        self.color = fields[1]
        self.arrival = int(fields[2])
        self.duration = int(fields[3])
        self.period = int(fields[4])
        self.deadline = int(fields[5])

        self._initialize_runtime(instance_number=1)
        # A suspensão da família também é herdada por liberações ainda não criadas.
        self.starts_suspended = False
        self.update_deadlines()

        if len(fields) > 6 and fields[6]:
            self.events = ast.literal_eval(fields[6])
        else:
            self.events = []

    def _initialize_runtime(self, instance_number):
        self.computational_time = 0
        self.instance_number = instance_number
        self.processor = None
        self.is_late = False
        self.state = NEW
        # A posição na fila é atribuída quando a instância entra no sistema.
        self.state_order = 0

    def update_deadlines(self):
        # Período e prazo relativo são independentes: a próxima liberação pode
        # ocorrer antes de esta instância terminar ou ultrapassar seu prazo.
        self.end_period = self.arrival + self.period
        self.absolute_deadline = self.arrival + self.deadline

    def create_next_instance(self):
        """Herda as características da família e reinicia apenas o estado da ocorrência."""
        # Os valores já foram validados; não é preciso remontar e interpretar
        # uma linha de configuração para construir cada ocorrência periódica.
        next_instance = TCB.__new__(TCB)

        next_instance.id = self.id
        next_instance.color = self.color
        next_instance.duration = self.duration
        next_instance.period = self.period
        next_instance.deadline = self.deadline
        next_instance.events = list(self.events)
        next_instance.starts_suspended = self.starts_suspended

        next_instance._initialize_runtime(self.instance_number + 1)
        next_instance.arrival = self.end_period
        next_instance.update_deadlines()

        return next_instance

    def __str__(self):
        return (
            f"Task ID {self.id}:\n"
            f"  - Color: {self.color}\n"
            f"  - Arrival: {self.arrival}\n"
            f"  - Duration: {self.duration}\n"
            f"  - Period: {self.period}\n"
            f"  - Deadline: {self.deadline}\n"
            f"  - Events: {self.events}\n"
            f"  - Computational Time: {self.computational_time}\n"
            f"  - Instance Number: {self.instance_number}\n"
            f"  - End Period: {self.end_period}\n"
            f"  - Absolute Deadline: {self.absolute_deadline}\n"
            f"  - Is Late: {self.is_late}"
        )
