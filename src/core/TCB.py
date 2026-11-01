"""Bloco de controle por instância, separado de processadores e renderização."""
import ast

# Estados possíveis de uma instância (como um enum em C).
# O nome em português é o mesmo que aparece na interface.
NEW = "Nova"                # ainda não chegou
READY = "Pronta"            # chegou e espera por uma CPU
RUNNING = "Executando"      # está em uma CPU
SUSPENDED = "Suspensa"      # chegou, mas foi suspensa manualmente
FINISHED = "Finalizada"     # terminou de executar
REMOVED = "Removida"        # foi removida pelo usuário


# Estado de uma instância periódica, incluindo características e consumo de CPU.
class TCB:
    def __init__(self, task_line):
        # 1. Pré-processamento: remove espaços em branco das extremidades
        fields = [field.strip() for field in task_line]

        # 2. Atribuição dos campos base (equivalente aos membros de uma struct em C)
        self.id = int(fields[0])
        self.color = fields[1]
        self.arrival = int(fields[2])
        self.duration = int(fields[3])
        self.period = int(fields[4])
        self.deadline = int(fields[5])

        # 3. Estado dinâmico de execução
        self.computational_time = 0
        self.instance_number = 1
        self.processor = None
        self.is_late = False
        # Estado atual da instância (um dos valores acima) e a ordem em que entrou nele.
        # A ordem faz o papel da posição na fila: quem entrou antes fica na frente.
        self.state = NEW
        self.state_order = 0
        # A suspensão manual vale para a família e acompanha novas cópias.
        # Se for verdadeira, a instância chega ao ingresso já suspensa, sem entrar na fila de prontos.
        self.starts_suspended = False

        # 4. Prazos absolutos calculados
        self.end_period = self.arrival + self.period
        self.absolute_deadline = self.arrival + self.deadline

        # 5. Lista de eventos opcionais
        if len(fields) > 6 and fields[6]:
            self.events = ast.literal_eval(fields[6])
        else:
            self.events = []

    # Deriva o próximo ingresso pelo período e calcula seu próprio prazo absoluto.
    def create_next_instance(self):
        # Cria uma nova instância vazia sem reprocessar strings
        next_instance = TCB.__new__(TCB)

        # Copia características estáticas do descritor de tarefa
        next_instance.id = self.id
        next_instance.color = self.color
        next_instance.duration = self.duration
        next_instance.period = self.period
        next_instance.deadline = self.deadline
        next_instance.events = list(self.events)  # Cópia rasa da lista de eventos
        next_instance.starts_suspended = self.starts_suspended

        # Inicializa estado dinâmico da nova instância
        next_instance.instance_number = self.instance_number + 1
        next_instance.computational_time = 0
        next_instance.processor = None
        next_instance.is_late = False
        next_instance.state = NEW
        next_instance.state_order = 0

        # Atualiza a linha temporal para o próximo ciclo periódico
        next_instance.arrival = self.end_period
        next_instance.end_period = next_instance.arrival + next_instance.period
        next_instance.absolute_deadline = next_instance.arrival + next_instance.deadline

        return next_instance

    # Descreve características e estado dinâmico para os logs da simulação.
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
