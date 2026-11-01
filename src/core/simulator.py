"""Relógio em ticks, liberações periódicas e aplicação de decisões por eventos."""
from copy import deepcopy
import random

from TCB import NEW, READY, RUNNING, SUSPENDED, FINISHED
from choose_task import choose_task, draws, get_algorithm, normalize_algorithm
from extract_config import extract_configuration
from simulation_state import simulation_state
from state_editor import edit_state
from task_fields import positive_integer, validate_changes
from simulation_result import Event, TaskInfo, SimulationResult, SIMULATION_LIMIT
from utils import initialize_processors, pair_cpus_tasks


def load_system(file_path, log):
    algorithm, quantum, num_cpus, task_list = extract_configuration(file_path, log)

    log.append(f"algorithm {algorithm}")
    log.append(f"quantum {quantum}")
    log.append(f"num_cpus {num_cpus}")

    return algorithm, quantum, num_cpus, task_list


def check_task(task, seen_ids, seen_colors):
    if task.id in seen_ids or task.color in seen_colors:
        raise ValueError('Identificadores e cores precisam ser exclusivos por tarefa.')
    # Os tempos já passaram por validate_changes; o ID fixo é validado aqui.
    if task.id <= 0:
        raise ValueError('A definição periódica contém um tempo ou identificador inválido.')


def start_simulation(algorithm, num_cpus, task_list):
    """Cria o instante zero sem reutilizar TCBs que possam pertencer a outra simulação."""
    algorithm = normalize_algorithm(algorithm)
    num_cpus = positive_integer(num_cpus, 'Número de processadores')
    tasks = deepcopy(task_list)

    seen_ids = set()
    seen_colors = set()
    for task in tasks:
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


def release_arrivals(state):
    # Uma redução de período pode deixar várias liberações vencidas. O laço
    # também admite as sucessoras geradas agora que já deveriam ter chegado.
    while True:
        arrived = [task for task in state.tasks_in(NEW) if task.arrival <= state.tick]
        if not arrived:
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


def check_deadlines(state):
    # Atraso é registrado uma única vez e não encerra nem bloqueia a instância.
    active_tasks = state.tasks_in(READY) + state.tasks_in(RUNNING) + state.tasks_in(SUSPENDED)
    for task in active_tasks:
        if task.absolute_deadline <= state.tick and not task.is_late:
            state.log.append(
                f"SCHEADULING ERROR: Task {task.id}({task.instance_number}) "
                f"has not completed its execution within its deadline at tick {state.tick}.")
            state.result.events.append(Event("deadline_miss", state.tick, task.id, task.instance_number))
            task.is_late = True


def schedule_if_needed(state):
    # RM/EDF não registram tick_event: só chegadas, liberações de CPU e edições
    # relevantes pedem uma nova seleção. Um prazo vencido sozinho não pede.
    policy = get_algorithm(state.algorithm)
    if policy.tick_event is not None and policy.tick_event(state):
        state.reschedule_needed = True
    if state.reschedule_needed:
        state.reschedule_needed = False
        if state.tasks_in(READY):
            schedule(state)


def schedule(state):
    state.log.append(f"A specific event triggered the scheduler in tick {state.tick}.")
    previously_running = tuple(state.tasks_in(RUNNING))
    candidates = state.tasks_in(READY) + list(previously_running)

    # O gerador de números aleatórios faz parte do estado: voltar e avançar
    # de novo repete exatamente os mesmos sorteios.
    rng = random.Random()
    rng.setstate(state.random_state)
    draws.clear()

    selected = []
    vacancies = min(len(state.processors_list), len(candidates))
    for _ in range(vacancies):
        chosen = choose_task(candidates, state.algorithm, rng, state)
        candidates.remove(chosen)
        selected.append(chosen)
    state.random_state = rng.getstate()

    record_draws(state, selected, previously_running)

    # Se a escolha é a mesma de antes, não mexe nas filas nem nas CPUs.
    if set(selected) == set(previously_running):
        return
    apply_selection(state, selected, previously_running)


def record_draws(state, selected, previously_running):
    # Comparações intermediárias podem sortear tarefas que não ganham uma CPU.
    # O gráfico mostra apenas sorteios que efetivamente causaram um despacho.
    selected = set(selected)
    for winner, loser in draws:
        if winner in selected and loser not in selected and winner not in previously_running:
            state.result.events.append(Event("draw", state.tick, winner.id, winner.instance_number))


def apply_selection(state, selected, previously_running):
    selected_set = set(selected)
    running_set = set(previously_running)
    for task in previously_running:
        if task not in selected_set:
            state.change_state(task, READY)
    for task in selected:
        if task not in running_set:
            state.change_state(task, RUNNING)
    pair_cpus_tasks(state.tasks_in(RUNNING), state.processors_list)


def execute_tick(state):
    """Executa [tick, tick+1) e registra a ocupação, mesmo se a instância terminar."""
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


def finish_task(state, task):
    # O término pertence ao limite direito do intervalo. A vaga é aproveitada
    # pelo próximo despacho, antes de executar o intervalo que começa ali.
    state.result.events.append(Event("finish", state.tick + 1, task.id, task.instance_number))
    state.change_state(task, FINISHED)
    if state.tasks_in(READY):
        state.reschedule_needed = True
    if task.instance_number == SIMULATION_LIMIT:
        state.log.append(
            f"Task {task.id}({task.instance_number}) has executed {SIMULATION_LIMIT} times "
            f"and has reached the simulation limit at tick {state.tick} -> {state.tick + 1}.")


def scale(current_state):
    """Constrói o próximo retrato, processando eventos antes de consumir CPU."""
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

    result.timeline.append(tick_row)
    result.suspended_timeline.append([(task.id, task.instance_number)
                                      for task in state.tasks_in(SUSPENDED)])
    state.tick += 1
    result.total_ticks = state.tick
    state.refresh_result()
    return state


class Simulator:
    """Ponto de acesso da GUI e do console ao histórico.

    history[t] guarda o retrato do tick t. Voltar descarta o último retrato;
    avançar recalcula o futuro, incluindo os mesmos sorteios guardados no estado.
    """
    def __init__(self):
        self.history = []

    def reset(self):
        self.history = []

    def is_loaded(self):
        return bool(self.history)

    def current(self):
        return self.history[-1]

    def load(self, file_path):
        """Substitui a simulação; falhas deixam o histórico vazio e preservam o diagnóstico."""
        log = []
        try:
            algorithm, quantum, num_cpus, task_list = load_system(file_path, log)
            state = start_simulation(algorithm, num_cpus, task_list)
        except ValueError as error:
            self.history = []
            raise ValueError("\n".join(log + [str(error)]))
        state.log = log
        self.history = [state]

    def step_forward(self):
        if not self.current().is_finished:
            self.history.append(scale(self.current()))
        return self.current()

    def can_step_back(self):
        return len(self.history) > 1

    def step_back(self):
        if self.can_step_back():
            self.history.pop()
        return self.current()

    def run_to_end(self):
        """Para também quando só resta suspensão manual, que não pode se resolver sozinha."""
        while not self.current().is_finished and not self.current().is_blocked:
            self.step_forward()
        return self.current()

    def edit(self, **changes):
        # Só substitui o retrato depois da transação validada; editar não cria tick.
        edited = edit_state(self.current(), **changes)
        self.history[-1] = edited
        return edited
