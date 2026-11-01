"""Relógio em ticks, liberações periódicas e aplicação de decisões por eventos."""
from utils import initialize_processors, pair_cpus_tasks
from extract_config import extract_system_parameters, extract_task_list
from choose_task import choose_task, draws, get_algorithm, normalize_algorithm
from copy import deepcopy
import random

from TCB import NEW, READY, RUNNING, SUSPENDED, FINISHED
from simulation_state import simulation_state
from state_editor import edit_state
from task_fields import positive_integer, validate_changes
from simulation_result import Event, TaskInfo, SimulationResult, SIMULATION_LIMIT


# Lê o arquivo de configuração e confere se o sistema é válido.
# Avisos e notas vão para o log (lista de textos). Em caso de erro, levanta ValueError.
def load_system(file_path, log):
    algorithm, quantum, num_cpus = extract_system_parameters(file_path, log)
    task_list = extract_task_list(file_path, log)

    log.append(f"algorithm {algorithm}")
    log.append(f"quantum {quantum}")
    log.append(f"num_cpus {num_cpus}")

    return algorithm, quantum, num_cpus, task_list


# Confere uma tarefa antes de iniciar a simulação (a lista recebida não é alterada).
def check_task(task, seen_ids, seen_colors):
    if task.id in seen_ids or task.color in seen_colors:
        raise ValueError('Identificadores e cores precisam ser exclusivos por tarefa.')
    if task.period <= 0 or task.deadline <= 0 or task.duration <= 0 or task.arrival < 0 or task.id <= 0:
        raise ValueError('A definição periódica contém um tempo ou identificador inválido.')


# Cria o estado do tick 0, com cópias das tarefas e uma CPU por identificador.
def start_simulation(algorithm, num_cpus, task_list):
    algorithm = normalize_algorithm(algorithm)
    num_cpus = positive_integer(num_cpus, 'Número de processadores')
    tasks = deepcopy(task_list)

    seen_ids = set()
    seen_colors = set()
    for task in tasks:
        # validate_changes normaliza os campos (ex.: cor em maiúsculas)
        for field, value in validate_changes(task, {}).items():
            setattr(task, field, value)
        check_task(task, seen_ids, seen_colors)
        seen_ids.add(task.id)
        seen_colors.add(task.color)

    result = SimulationResult(algorithm, num_cpus, [TaskInfo(task) for task in tasks])
    initial_state = simulation_state(
        algorithm=algorithm,
        processors_list=initialize_processors(num_cpus),
        tasks=tasks,
        result=result,
    )
    return initial_state


# ---------- Etapas de um tick ----------

# Passo 1: tarefas Novas cuja chegada já aconteceu passam para Pronta (ou Suspensa)
# e já agendam a próxima instância.
def release_arrivals(state):
    while True:
        arrived = [task for task in state.tasks_in(NEW) if task.arrival <= state.tick]
        if len(arrived) == 0:
            break
        for task in arrived:
            if task.starts_suspended:
                state.change_state(task, SUSPENDED)
            else:
                state.change_state(task, READY)
                state.reschedule_needed = True
            state.result.events.append(Event("arrival", state.tick, task.id, task.instance_number))
            state.enqueue_next_instance(task)
            state.log.append(f"Task {task.id}({task.instance_number}) has arrived at tick {state.tick}.")


# Passo 2: marca (uma única vez) as instâncias que passaram do prazo.
# Estar atrasada é um evento: a tarefa continua na fila e pode terminar depois.
def check_deadlines(state):
    active_tasks = state.tasks_in(READY) + state.tasks_in(RUNNING) + state.tasks_in(SUSPENDED)
    for task in active_tasks:
        if task.absolute_deadline <= state.tick and not task.is_late:
            state.log.append(f"SCHEADULING ERROR: Task {task.id}({task.instance_number}) has not completed its execution within its deadline at tick {state.tick}.")
            state.result.events.append(Event("deadline_miss", state.tick, task.id, task.instance_number))
            task.is_late = True


# Passo 3: só chama o algoritmo quando houve um evento que pode mudar a decisão
# (chegada, CPU liberada, edição). Passar o relógio, sozinho, não reescalona.
def schedule_if_needed(state):
    policy = get_algorithm(state.algorithm)
    if policy.tick_event is not None and policy.tick_event(state):
        state.reschedule_needed = True
    if state.reschedule_needed:
        state.reschedule_needed = False
        if len(state.tasks_in(READY)) > 0:
            schedule(state)


# Escolhe as instâncias que devem executar (uma por CPU, no máximo) e aplica as trocas.
def schedule(state):
    state.log.append(f"A specific event triggered the scheduler in tick {state.tick}.")
    previously_running = tuple(state.tasks_in(RUNNING))
    candidates = state.tasks_in(READY) + state.tasks_in(RUNNING)

    # O gerador de números aleatórios faz parte do estado: voltar e avançar
    # de novo repete exatamente os mesmos sorteios.
    rng = random.Random()
    rng.setstate(state.random_state)
    draws.clear()

    selected = []
    vacancies = min(len(state.processors_list), len(candidates))
    for i in range(vacancies):
        chosen = choose_task(candidates, state.algorithm, rng, state)
        candidates.remove(chosen)
        selected.append(chosen)
    state.random_state = rng.getstate()

    record_draws(state, selected, previously_running)

    # Se a escolha é a mesma de antes, não mexe nas filas nem nas CPUs.
    if set(selected) == set(previously_running):
        return
    apply_selection(state, selected, previously_running)


# Registra o evento "sorteio" quando o sorteio colocou uma tarefa nova para executar.
def record_draws(state, selected, previously_running):
    for winner, loser in draws:
        if winner in selected and loser not in selected and winner not in previously_running:
            state.result.events.append(Event("draw", state.tick, winner.id, winner.instance_number))


# Tira da CPU quem perdeu a vaga, coloca para executar quem ganhou e liga tarefas às CPUs.
def apply_selection(state, selected, previously_running):
    for task in previously_running:
        if task not in selected:
            state.change_state(task, READY)
    for task in selected:
        if task not in previously_running:
            state.change_state(task, RUNNING)
    pair_cpus_tasks(state.tasks_in(RUNNING), state.processors_list)


# Passo 4: cada CPU executa 1 tick. Devolve o que cada CPU fez (None = CPU parada).
def execute_tick(state):
    tick_row = []
    for cpu in state.processors_list:
        if cpu.task_running is None:
            tick_row.append(None)
            state.log.append(f"Processor: {cpu.id}: No task is running at tick {state.tick} -> {state.tick + 1}.")
            continue

        task = cpu.task_running
        tick_row.append((task.id, task.instance_number))
        state.log.append(f"Processor {cpu.id}: Task {task.id}({task.instance_number}) is running at tick {state.tick} -> {state.tick + 1}.")
        task.computational_time += 1

        if task.computational_time >= task.duration:
            finish_task(state, task)
    return tick_row


# Termina uma instância: o estado vira FINISHED e a CPU é liberada.
def finish_task(state, task):
    state.result.events.append(Event("finish", state.tick + 1, task.id, task.instance_number))
    state.change_state(task, FINISHED)
    if len(state.tasks_in(READY)) > 0:
        state.reschedule_needed = True
    if task.instance_number == SIMULATION_LIMIT:
        state.log.append(f"Task {task.id}({task.instance_number}) has executed {SIMULATION_LIMIT} times and has reached the simulation limit at tick {state.tick} -> {state.tick + 1}.")


# Constrói o próximo estado (tick + 1) sem modificar o estado recebido nem o histórico.
def scale(current_state):
    if current_state.is_finished:
        return current_state

    # Uma única cópia preserva os vínculos entre tarefas, filas e processadores
    # (tarefa.processor e cpu.task_running apontam um para o outro).
    state = deepcopy(current_state)
    result = state.result

    state.log.append(f"==================== TICK: {state.tick} ===================")

    release_arrivals(state)
    check_deadlines(state)
    schedule_if_needed(state)
    tick_row = execute_tick(state)

    # Registra o que aconteceu neste tick para o gráfico de Gantt
    result.timeline.append(tick_row)
    result.suspended_timeline.append([(task.id, task.instance_number)
                                      for task in state.tasks_in(SUSPENDED)])
    state.tick = state.tick + 1
    result.total_ticks = state.tick
    state.refresh_result()
    return state


# Guarda o histórico da simulação e é a única interface usada pela janela e pelo console.
#
#   history[t] é o estado no tick t; o último é o estado atual
#   (parecido com um vetor de structs em C, uma cópia por tick).
#
# Avançar calcula um novo estado e o acrescenta ao fim; voltar descarta o último.
# Voltar e avançar de novo dá o mesmo resultado, porque o estado guarda também o gerador
# de números aleatórios (os sorteios de desempate se repetem).
class Simulator:
    def __init__(self):
        self.history = []

    # Esquece a simulação carregada.
    def reset(self):
        self.history = []

    # Diz se já existe uma configuração carregada.
    def is_loaded(self):
        return len(self.history) > 0

    # Estado atual (o último do histórico).
    def current(self):
        return self.history[-1]

    # Lê o arquivo de configuração e cria o estado do tick 0.
    # Em caso de erro, levanta ValueError com o log e o motivo do erro.
    def load(self, file_path):
        log = []
        try:
            algorithm, quantum, num_cpus, task_list = load_system(file_path, log)
            state = start_simulation(algorithm, num_cpus, task_list)
        except ValueError as error:
            self.history = []
            raise ValueError("\n".join(log + [str(error)]))
        state.log = log
        self.history = [state]

    # Simula mais um tick (não faz nada se a simulação já terminou). Devolve o novo estado atual.
    def step_forward(self):
        if not self.current().is_finished:
            self.history.append(scale(self.current()))
        return self.current()

    # Diz se existe um tick anterior para onde voltar.
    def can_step_back(self):
        return len(self.history) > 1

    # Descarta o último tick e devolve o estado anterior, sem recalculá-lo.
    def step_back(self):
        if self.can_step_back():
            self.history.pop()
        return self.current()

    # Avança até a simulação terminar (ou parar numa suspensão manual que só o usuário retoma).
    def run_to_end(self):
        while not self.current().is_finished and not self.current().is_blocked:
            self.step_forward()
        return self.current()

    # Aplica uma edição (ver state_editor.edit_state) ao estado atual.
    # Se for inválida, levanta ValueError e nada muda. Editar não cria um tick novo.
    def edit(self, **changes):
        edited = edit_state(self.current(), **changes)
        self.history[-1] = edited
        return edited
