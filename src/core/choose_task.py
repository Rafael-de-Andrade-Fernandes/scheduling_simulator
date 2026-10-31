import random

# Sorteios feitos na rodada atual: lista de pares (vencedora, perdedora).
# É como um vetor global em C: o simulador esvazia a lista a cada tick
# e depois a consulta para mostrar o evento "sorteio" no gráfico de Gantt.
draws = []

def sort_tie(t1, t2):
    winner = random.choice([t1, t2])
    loser = t2 if winner is t1 else t1
    draws.append((winner, loser))
    return winner

# Desempate
def break_tie(t1, t2):
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
    return sort_tie(t1, t2)


# Rate Monotonic: ganha quem tem o menor período
def compare_tasks_rm(t1, t2):
    if t1.period != t2.period:
        return t1 if t1.period < t2.period else t2
    return break_tie(t1, t2)


# Earliest Deadline First: ganha quem tem o prazo absoluto mais próximo
# (absolute_deadline = instante em que a instância atual precisa terminar)
def compare_tasks_edf(t1, t2):
    if t1.absolute_deadline != t2.absolute_deadline:
        return t1 if t1.absolute_deadline < t2.absolute_deadline else t2
    return break_tie(t1, t2)


# Algoritmos disponíveis: nome usado no arquivo de configuração -> função que
# compara duas tarefas e devolve a mais prioritária.
# Para incluir um novo algoritmo basta escrever sua função de comparação acima
# e acrescentar uma linha aqui (não é preciso mexer no código da simulação).
SCHEDULERS = {
    'RM': compare_tasks_rm,
    'EDF': compare_tasks_edf,
}


def choose_task(tasks, algorithm):
    if not tasks:
        return None

    if algorithm not in SCHEDULERS:
        return None
    compare = SCHEDULERS[algorithm]

    chosen = tasks[0]
    # Itera como um loop for (int i = 1; i < n; i++) em C
    for i in range(1, len(tasks)):
        chosen = compare(chosen, tasks[i])
    return chosen
