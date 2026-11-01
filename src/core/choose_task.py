"""Algoritmos de escalonamento (RM, EDF) e regras de desempate."""
import random


class SchedulingAlgorithm:
    """Política de seleção, com extensões para eventos e edições que afetam a prioridade.

    ``primary_key`` ordena as candidatas; ``selector`` pode substituir essa escolha.
    ``tick_event`` sinaliza eventos da própria política, como um quantum. A assinatura
    de edição evita reescalonar por mudanças que não alteram a prioridade.
    """
    def __init__(self, name, primary_key, selector=None, tick_event=None, edit_signature=None):
        self.name = name
        self.primary_key = primary_key
        self.selector = selector
        self.tick_event = tick_event
        self.edit_signature = edit_signature

    def priority_signature(self, task):
        if self.edit_signature is not None:
            return self.edit_signature(task)
        return (self.primary_key(task), task.deadline, task.arrival, task.duration)

    def compare(self, first, second, rng=None):
        first_key = self.primary_key(first)
        second_key = self.primary_key(second)
        if first_key != second_key:
            return first if first_key < second_key else second
        return break_tie(first, second, rng)


ALGORITHMS = {}


def register_algorithm(name, primary_key=None, selector=None, tick_event=None, edit_signature=None):
    """Registra uma política reconhecida pelo carregador, pela edição e pela interface."""
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


def available_algorithms():
    return tuple(ALGORITHMS)


def normalize_algorithm(name):
    name = str(name).strip().upper()
    if name not in ALGORITHMS:
        raise ValueError("Algoritmo inválido. Digite " + " ou ".join(ALGORITHMS) + ".")
    return name


def get_algorithm(name):
    return ALGORITHMS[normalize_algorithm(name)]


# A rodada de seleção limpa esta lista. Só os pares que causarem um novo
# despacho serão transformados em eventos do Gantt pelo simulador.
draws = []

def sort_tie(t1, t2, rng=None):
    winner = (rng if rng is not None else random).choice([t1, t2])
    loser = t2 if winner is t1 else t1
    draws.append((winner, loser))
    return winner

def break_tie(t1, t2, rng=None):
    """Desempata por execução atual, prazo relativo, ingresso, duração e sorteio."""
    # Preservar a incumbente evita uma preempção sem ganho de prioridade.
    has_proc1 = 1 if t1.processor else 0
    has_proc2 = 1 if t2.processor else 0

    if has_proc1 != has_proc2:
        return t1 if has_proc1 > has_proc2 else t2

    if t1.deadline != t2.deadline:
        return t1 if t1.deadline < t2.deadline else t2

    if t1.arrival != t2.arrival:
        return t1 if t1.arrival < t2.arrival else t2

    if t1.duration != t2.duration:
        return t1 if t1.duration < t2.duration else t2

    return sort_tie(t1, t2, rng)


def choose_task(tasks, algorithm, rng=None, state=None):
    """Escolhe uma candidata; a aplicação da troca fica a cargo do simulador."""
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
    for task in tasks[1:]:
        chosen = compare(chosen, task, rng)
    return chosen


# As políticas concretas ficam apenas neste registro; menor chave = maior prioridade.
register_algorithm('RM', lambda task: task.period)
register_algorithm('EDF', lambda task: task.absolute_deadline)
