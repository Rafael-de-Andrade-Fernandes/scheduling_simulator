"""Retrato da simulação em um instante: tarefas, CPUs, relógio e registros do gráfico."""
import random

from TCB import NEW, READY, RUNNING, SUSPENDED, FINISHED, REMOVED
from simulation_result import SIMULATION_LIMIT
from choose_task import available_algorithms

ACTIVE_STATES = (NEW, READY, RUNNING, SUSPENDED)


class simulation_state:
    """Retrato completo de um instante, copiado pelo simulador antes de avançar.

    all_tasks é a fonte única dos TCBs. As filas são consultas por estado e
    state_order, sem listas paralelas para sincronizar. Mudanças passam por
    change_state para manter essa ordem e os vínculos com as CPUs coerentes.
    """
    def __init__(self, algorithm, processors_list, tasks, result):
        self.tick = 0
        self.algorithm = algorithm
        self.processors_list = processors_list
        self.all_tasks = []
        self.next_order = 0
        for task in tasks:
            self.append_task(task)
        self.result = result
        # O log pertence ao retrato: voltar descarta também as mensagens do futuro.
        self.log = []
        self.random_state = random.getstate()
        # Eventos no limite de um tick são consumidos no próximo despacho,
        # antes de executar o intervalo que começa nesse mesmo instante.
        self.reschedule_needed = False

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

    def change_state(self, task, new_state):
        """Libera a CPU anterior e posiciona a instância no fim da nova fila."""
        self.release_cpu(task)
        task.state = new_state
        task.state_order = self.next_order
        self.next_order += 1

    def release_cpu(self, task):
        if task.processor is not None:
            task.processor.task_running = None
            task.processor = None

    def discard(self, task):
        # Uma liberação cancelada antes do ingresso não deve gerar chegada ou término.
        self.release_cpu(task)
        self.all_tasks.remove(task)

    def info_of(self, task_id):
        return next(info for info in self.result.tasks if info.id == task_id)

    def is_removed(self, task_id):
        for info in self.result.tasks:
            if info.id == task_id:
                return info.removed_tick is not None
        return False

    def current_task(self, task_id):
        """Consulta a mais antiga ainda ativa ou a última concluída da definição."""
        # Antiguidade usa instance_number; state_order muda nas trocas de fila.
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

    @property
    def is_finished(self):
        return not any(task.state in ACTIVE_STATES for task in self.all_tasks)

    @property
    def is_blocked(self):
        # Mesmo suspensa, a família pode ter liberações futuras a processar.
        has_suspended = any(task.state == SUSPENDED for task in self.all_tasks)
        has_other_work = any(task.state in (NEW, READY, RUNNING) for task in self.all_tasks)
        return has_suspended and not has_other_work

    def enqueue_next_instance(self, task):
        """Agenda a sucessora pela data periódica, independentemente do término atual."""
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

    def refresh_result(self):
        self.result.algorithm = self.algorithm
        self.result.num_cpus = len(self.processors_list)
        self.result.current_suspended = [(task.id, task.instance_number)
                                         for task in self.tasks_in(SUSPENDED)]

    @property
    def algorithm_options(self):
        return available_algorithms()
