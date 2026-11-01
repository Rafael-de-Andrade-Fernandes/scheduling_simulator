"""Retrato da simulação em um instante: tarefas, CPUs, relógio e registros do gráfico."""
import random

from TCB import NEW, READY, RUNNING, SUSPENDED, FINISHED, REMOVED
from simulation_result import SIMULATION_LIMIT
from choose_task import available_algorithms

# Estados de uma instância que ainda não terminou nem foi removida, na ordem de consulta
ACTIVE_STATES = (NEW, READY, RUNNING, SUSPENDED)


# Um retrato completo da simulação em um instante de tempo (uma "struct" copiada a cada tick).
#
# Todas as instâncias de tarefas ficam em UMA lista (all_tasks). Cada instância tem um
# campo "state" (NEW, READY, RUNNING...). As "filas" não existem como listas:
# tasks_in(READY) devolve as instâncias que estão naquele estado, na ordem em que entraram.
# Toda mudança de estado passa por change_state().
#
# As edições feitas pelo usuário estão em state_editor.py.
class simulation_state:
    def __init__(self, algorithm, processors_list, tasks, result):
        self.tick = 0
        self.algorithm = algorithm
        self.processors_list = processors_list
        self.all_tasks = []
        self.next_order = 0
        for task in tasks:
            self.append_task(task)
        self.result = result
        # Mensagens da simulação, uma por linha (cada estado guarda as suas, para o "voltar" funcionar)
        self.log = []
        self.random_state = random.getstate()
        # Eventos no limite de um tick são consumidos no próximo despacho,
        # antes de executar o intervalo que começa nesse mesmo instante.
        self.reschedule_needed = False

    # Acrescenta uma instância nova (estado NEW) à lista de tarefas.
    def append_task(self, task):
        task.state = NEW
        task.state_order = self.next_order
        self.next_order += 1
        self.all_tasks.append(task)

    # Lista as instâncias que estão em um estado, na ordem em que entraram nele.
    def tasks_in(self, wanted_state):
        found = [task for task in self.all_tasks if task.state == wanted_state]
        found.sort(key=lambda task: task.state_order)
        return found

    # Lista as instâncias ainda não concluídas (nem removidas) de uma tarefa.
    def active_instances(self, task_id):
        instances = []
        for wanted_state in ACTIVE_STATES:
            for task in self.tasks_in(wanted_state):
                if task.id == task_id:
                    instances.append(task)
        return instances

    # Muda o estado de uma instância. É o único lugar que faz isso.
    # Ao sair de uma CPU (qualquer mudança de estado), libera a CPU que ela ocupava.
    def change_state(self, task, new_state):
        self.release_cpu(task)
        task.state = new_state
        task.state_order = self.next_order
        self.next_order += 1

    # Desliga a ligação entre a instância e a CPU em que estava.
    def release_cpu(self, task):
        if task.processor is not None:
            task.processor.task_running = None
            task.processor = None

    # Descarta uma instância futura cancelada: ela some do sistema sem deixar registro.
    def discard(self, task):
        self.release_cpu(task)
        self.all_tasks.remove(task)

    # Dados de apresentação (cor, prazos...) da tarefa com esse ID.
    def info_of(self, task_id):
        return next(info for info in self.result.tasks if info.id == task_id)

    # Diz se a tarefa com esse ID já foi removida pelo usuário.
    def is_removed(self, task_id):
        for info in self.result.tasks:
            if info.id == task_id:
                return info.removed_tick is not None
        return False

    # Escolhe a instância ativa mais antiga ou a última concluída para inspeção.
    # Devolve (instância, nome do estado).
    def current_task(self, task_id):
        # O número da instância mantém a ordem de criação mesmo após editar o ingresso.
        if self.is_removed(task_id):
            cancelled = [task for task in self.all_tasks if task.id == task_id and task.state == REMOVED]
            if cancelled:
                return min(cancelled, key=lambda task: task.instance_number), REMOVED
            history = [task for task in self.all_tasks if task.id == task_id and task.state == FINISHED]
            if history:
                return max(history, key=lambda task: task.instance_number), REMOVED
        active = self.active_instances(task_id)
        if active:
            oldest = min(active, key=lambda task: task.instance_number)
            return oldest, oldest.state
        completed = [task for task in self.all_tasks if task.id == task_id and task.state == FINISHED]
        if completed:
            return max(completed, key=lambda task: task.instance_number), FINISHED
        raise ValueError(f"A tarefa {task_id} não existe no estado atual.")

    # Indica ausência de trabalho ativo ou futuro; suspensão não é conclusão.
    @property
    def is_finished(self):
        return not any(task.state in ACTIVE_STATES for task in self.all_tasks)

    # Detecta espera exclusiva por retomada manual, sem liberação futura pendente.
    @property
    def is_blocked(self):
        has_suspended = len(self.tasks_in(SUSPENDED)) > 0
        has_other_work = any(task.state in (NEW, READY, RUNNING) for task in self.all_tasks)
        return has_suspended and not has_other_work

    # Agenda a próxima liberação por período, sem duplicar ou ultrapassar dez instâncias.
    def enqueue_next_instance(self, task):
        if task.instance_number >= SIMULATION_LIMIT or self.is_removed(task.id):
            return None
        next_number = task.instance_number + 1
        # Uma edição ou admissão manual pode já ter agendado a próxima liberação.
        for other in self.all_tasks:
            if other.id == task.id and other.instance_number == next_number:
                return None
        next_instance = task.create_next_instance()
        self.append_task(next_instance)
        return next_instance

    # Atualiza somente os metadados correntes usados pelo desenho.
    def refresh_result(self):
        self.result.algorithm = self.algorithm
        self.result.num_cpus = len(self.processors_list)
        self.result.current_suspended = [(task.id, task.instance_number)
                                         for task in self.tasks_in(SUSPENDED)]

    # Consulta o registro compartilhado, sem nomes concretos fixos na interface.
    @property
    def algorithm_options(self):
        return available_algorithms()
