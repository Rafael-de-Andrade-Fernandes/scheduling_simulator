import contextlib
import copy
import io

from extract_config import extract_system_parameters, extract_task_list
from simulation_state import SimulationState
from task_editor import edit_task, set_algorithm, set_num_cpus
from tick import advance_one_tick
from view import build_view

# Limite de segurança: evita um laço infinito se algo impedir as tarefas de terminarem
MAX_TICKS = 100000


# Lê o arquivo de configuração e confere se o sistema é válido.
# Em caso de erro, imprime o motivo e chama exit(1) (como nas outras funções de leitura).
def load_system(file_path):
    algorithm, quantum, num_cpus = extract_system_parameters(file_path)
    task_list = extract_task_list(file_path)

    print(f"algorithm {algorithm}")
    print(f"quantum {quantum}")
    print(f"num_cpus {num_cpus}")

    for task in task_list:
        task.print()
        # RM e EDF só aceitam tarefas com prazo igual ao período (Di = Pi)
        if task.period != task.deadline:
            print(f"Task {task.id} has a period different from its deadline. This is not allowed in RM or EDF scheduling. Exiting simulation.")
            exit(1)

    return algorithm, quantum, num_cpus, task_list


# Controla a simulação: avança, retrocede e guarda o histórico em memória.
# A parte gráfica só chama os métodos desta classe.
class Simulator:
    def __init__(self):
        # history guarda uma "foto" (SimulationState) de cada tick; a última é o estado atual
        self.history = []
        # future guarda os estados desfeitos por step_back, para o avanço repetir a mesma simulação
        # (sem isso o sorteio de desempate poderia dar outro resultado)
        self.future = []

    # Estado atual (a última foto do histórico)
    def current(self):
        return self.history[-1]

    # Lê o arquivo e começa uma nova simulação no tick 0.
    # Devolve (True, texto_da_leitura) ou (False, motivo_do_erro).
    # Se falhar, a simulação anterior continua como estava.
    def load(self, file_path):
        output = io.StringIO()
        try:
            with contextlib.redirect_stdout(output):
                algorithm, quantum, num_cpus, task_list = load_system(file_path)
        except SystemExit:
            return False, output.getvalue()

        state = SimulationState(algorithm, num_cpus, task_list)
        lines = output.getvalue().split("\n")
        state.log.extend(lines)
        for line in lines:
            if line.startswith("Warning"):
                state.warnings.append(line)

        self.history = [state]
        self.future = []
        return True, output.getvalue()

    # Avança um tick. Devolve "" se avançou ou o motivo de não ter avançado.
    def step_forward(self):
        if len(self.history) == 0:
            return "Nenhuma simulação carregada."
        if self.current().is_finished():
            return "A simulação já terminou."
        if self.current().tick >= MAX_TICKS:
            return f"Simulação interrompida: passou de {MAX_TICKS} ticks."

        if len(self.future) > 0:
            next_state = self.future.pop()
        else:
            next_state = copy.deepcopy(self.current())
            advance_one_tick(next_state)
        self.history.append(next_state)
        return ""

    # Volta um tick. Devolve "" se voltou ou o motivo de não ter voltado.
    def step_back(self):
        if len(self.history) == 0:
            return "Nenhuma simulação carregada."
        if len(self.history) == 1:
            return "A simulação já está no tick 0."
        self.future.append(self.history.pop())
        return ""

    # Executa até o fim (modo de execução completa)
    def run_to_end(self):
        message = ""
        while message == "" and not self.current().is_finished():
            message = self.step_forward()
        
        return message

    # Modifica uma tarefa no estado atual. Devolve (ok, mensagem).
    def edit_task(self, task_id, values):
        if len(self.history) == 0:
            return False, "Nenhuma simulação carregada."
        ok, message = edit_task(self.current(), task_id, values)
        if ok:
            self.future = []     # o futuro desfeito não vale mais
        return ok, message

    def set_algorithm(self, name):
        if len(self.history) == 0:
            return False, "Nenhuma simulação carregada."
        ok, message = set_algorithm(self.current(), name)
        if ok:
            self.future = []
        return ok, message

    def set_num_cpus(self, num_cpus):
        if len(self.history) == 0:
            return False, "Nenhuma simulação carregada."
        ok, message = set_num_cpus(self.current(), num_cpus)
        if ok:
            self.future = []
        return ok, message

    # Visão do estado atual para a parte gráfica (None se nada foi carregado)
    def view(self):
        if len(self.history) == 0:
            return None
        return build_view(self.current())
