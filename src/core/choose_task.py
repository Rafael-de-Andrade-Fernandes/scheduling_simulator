"""Registro extensível de políticas e regras comuns de desempate do Projeto A."""
import random
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class SchedulingAlgorithm:
    """Política registrada: prioridade primária e desempates comuns do enunciado."""
    name: str
    primary_key: Callable
    selector: Callable | None = None
    tick_event: Callable | None = None
    edit_signature: Callable | None = None

    def priority_signature(self, task):
        # Usada apenas ao editar: detecta se a alteração pode mudar a escolha.
        """Resume os dados que uma edição pode alterar na decisão desta política."""
        if self.edit_signature is not None:
            return self.edit_signature(task)
        return (self.primary_key(task), task.deadline, task.arrival, task.duration)

    def compare(self, first, second, rng=None):
        """Compara a prioridade primária e aplica os desempates comuns quando necessário."""
        first_key, second_key = self.primary_key(first), self.primary_key(second)
        if first_key != second_key:
            return first if first_key < second_key else second
        return break_tie(first, second, rng)


ALGORITHMS = {}


def register_algorithm(name, primary_key=None, *, selector=None, tick_event=None, edit_signature=None):
    """Acrescenta uma política sem alterar o relógio, o estado ou o carregador."""
    name = str(name).strip().upper()
    if not name or not name.isalnum() or not (callable(primary_key) or callable(selector)):
        raise ValueError("O algoritmo precisa de abreviação alfanumérica e função de prioridade.")
    if name in ALGORITHMS:
        raise ValueError(f"O algoritmo {name} já está registrado.")
    if any(value is not None and not callable(value) for value in (selector, tick_event, edit_signature)):
        raise ValueError("Os pontos de extensão do algoritmo precisam ser funções.")
    ALGORITHMS[name] = SchedulingAlgorithm(name, primary_key or (lambda task: 0), selector, tick_event, edit_signature)


def available_algorithms():
    """Expõe as abreviações registradas para a validação e os campos da interface."""
    return tuple(ALGORITHMS)


def normalize_algorithm(name):
    """Normaliza caixa e espaços usando o mesmo registro em todas as entradas."""
    name = str(name).strip().upper()
    if name not in ALGORITHMS:
        raise ValueError("Algoritmo inválido. Digite " + " ou ".join(ALGORITHMS) + ".")
    return name


def get_algorithm(name):
    """Obtém a política registrada, com erro explícito para uma abreviação desconhecida."""
    return ALGORITHMS[normalize_algorithm(name)]

# Sorteios feitos na rodada atual: lista de pares (vencedora, perdedora).
# É como um vetor global em C: o simulador esvazia a lista a cada escalonamento
# e depois a consulta para mostrar o evento "sorteio" no gráfico de Gantt.
draws = []

def sort_tie(t1, t2, rng=None):
    """Realiza o último desempate e registra o par para desenhar somente sorteios efetivos."""
    winner = (rng if rng is not None else random).choice([t1, t2])
    loser = t2 if winner is t1 else t1
    draws.append((winner, loser))
    return winner

# Desempate
def break_tie(t1, t2, rng=None):
    # 1. Tarefa que já está em execução no processador
    """Evita troca para a própria tarefa antes de comparar prazo, ingresso e duração."""
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


# Rate Monotonic: ganha quem tem o menor período
def compare_tasks_rm(t1, t2, rng=None):
    """Mantém a API RM, delegando sua prioridade ao registro central."""
    return get_algorithm('RM').compare(t1, t2, rng)


# Earliest Deadline First: ganha quem tem o prazo absoluto mais próximo
# (absolute_deadline = instante em que a instância atual precisa terminar)
def compare_tasks_edf(t1, t2, rng=None):
    """Mantém a API EDF, delegando sua prioridade ao registro central."""
    return get_algorithm('EDF').compare(t1, t2, rng)


def choose_task(tasks, algorithm, rng=None, state=None):
    """Seleciona uma candidata sem alterar as filas; a aplicação das trocas fica no núcleo."""
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


# Único ponto de definição das políticas concretas. Menor chave = maior prioridade.
register_algorithm('RM', lambda task: task.period)
register_algorithm('EDF', lambda task: task.absolute_deadline)
