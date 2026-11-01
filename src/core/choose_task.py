"""Algoritmos de escalonamento (RM, EDF) e regras de desempate."""
import random


# Um algoritmo de escalonamento. Funciona como uma struct com funções:
#   name          abreviação usada no arquivo de configuração (ex.: "RM")
#   primary_key   função que dá a "nota" da tarefa; menor nota = maior prioridade
#   selector      (opcional) função que escolhe a tarefa no lugar do primary_key
#   tick_event    (opcional) função chamada a cada tick; devolve True se precisa reescalonar
#   edit_signature (opcional) resumo dos dados que uma edição pode mudar na decisão
class SchedulingAlgorithm:
    def __init__(self, name, primary_key, selector=None, tick_event=None, edit_signature=None):
        self.name = name
        self.primary_key = primary_key
        self.selector = selector
        self.tick_event = tick_event
        self.edit_signature = edit_signature

    # Resume os dados que uma edição pode alterar na escolha desta política.
    def priority_signature(self, task):
        if self.edit_signature is not None:
            return self.edit_signature(task)
        return (self.primary_key(task), task.deadline, task.arrival, task.duration)

    # Devolve a tarefa mais prioritária entre duas (desempata se a nota for igual).
    def compare(self, first, second, rng=None):
        first_key = self.primary_key(first)
        second_key = self.primary_key(second)
        if first_key != second_key:
            return first if first_key < second_key else second
        return break_tie(first, second, rng)


# Tabela de algoritmos: nome -> SchedulingAlgorithm
ALGORITHMS = {}


# Acrescenta um algoritmo na tabela (sem mexer no relógio, no estado ou no carregador).
def register_algorithm(name, primary_key=None, selector=None, tick_event=None, edit_signature=None):
    name = str(name).strip().upper()
    if not name or not name.isalnum() or not (callable(primary_key) or callable(selector)):
        raise ValueError("O algoritmo precisa de abreviação alfanumérica e função de prioridade.")
    if name in ALGORITHMS:
        raise ValueError(f"O algoritmo {name} já está registrado.")
    for function in (selector, tick_event, edit_signature):
        if function is not None and not callable(function):
            raise ValueError("Os pontos de extensão do algoritmo precisam ser funções.")
    if primary_key is None:
        primary_key = lambda task: 0
    ALGORITHMS[name] = SchedulingAlgorithm(name, primary_key, selector, tick_event, edit_signature)


# Lista as abreviações dos algoritmos cadastrados.
def available_algorithms():
    return tuple(ALGORITHMS)


# Põe o nome em maiúsculas e confere se o algoritmo existe.
def normalize_algorithm(name):
    name = str(name).strip().upper()
    if name not in ALGORITHMS:
        raise ValueError("Algoritmo inválido. Digite " + " ou ".join(ALGORITHMS) + ".")
    return name


# Busca o algoritmo na tabela pelo nome.
def get_algorithm(name):
    return ALGORITHMS[normalize_algorithm(name)]


# Sorteios feitos na rodada atual: lista de pares (vencedora, perdedora).
# É como um vetor global em C: o simulador esvazia a lista a cada escalonamento
# e depois a consulta para mostrar o evento "sorteio" no gráfico de Gantt.
draws = []

# Último desempate: sorteia uma das duas e guarda o par em "draws".
def sort_tie(t1, t2, rng=None):
    winner = (rng if rng is not None else random).choice([t1, t2])
    loser = t2 if winner is t1 else t1
    draws.append((winner, loser))
    return winner

# Desempate: usado quando duas tarefas têm a mesma nota no algoritmo.
def break_tie(t1, t2, rng=None):
    # 1. Tarefa que já está em execução no processador
    has_proc1 = 1 if t1.processor else 0
    has_proc2 = 1 if t2.processor else 0

    if has_proc1 != has_proc2:
        return t1 if has_proc1 > has_proc2 else t2

    # 2. Menor deadline
    if t1.deadline != t2.deadline:
        return t1 if t1.deadline < t2.deadline else t2

    # 3. Menor tempo de chegada (arrival)
    if t1.arrival != t2.arrival:
        return t1 if t1.arrival < t2.arrival else t2

    # 4. Menor duração
    if t1.duration != t2.duration:
        return t1 if t1.duration < t2.duration else t2

    # 5. Empate total: sorteio
    return sort_tie(t1, t2, rng)


# Escolhe, entre as candidatas, a tarefa que deve executar segundo o algoritmo.
# Não mexe nas filas: quem aplica a troca é o simulador.
def choose_task(tasks, algorithm, rng=None, state=None):
    if not tasks:
        return None

    policy = get_algorithm(algorithm)
    if policy.selector is not None:
        chosen = policy.selector(tasks, state, rng)
        if chosen not in tasks:
            raise ValueError(f"O algoritmo {policy.name} retornou uma tarefa que não é candidata.")
        return chosen
    compare = policy.compare

    chosen = tasks[0]
    # Itera como um loop for (int i = 1; i < n; i++) em C
    for i in range(1, len(tasks)):
        chosen = compare(chosen, tasks[i], rng)
    return chosen


# Algoritmos disponíveis. Menor nota = maior prioridade.
#   RM:  ganha quem tem o menor período
#   EDF: ganha quem tem o prazo absoluto mais próximo
# Para incluir outro algoritmo, basta acrescentar uma linha aqui.
register_algorithm('RM', lambda task: task.period)
register_algorithm('EDF', lambda task: task.absolute_deadline)
