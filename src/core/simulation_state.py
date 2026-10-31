import ast
from copy import deepcopy
import random
import re

from processor import processor
from simulation_result import Event, SIMULATION_LIMIT


TASK_STATES = ("Nova", "Pronta", "Executando", "Suspensa", "Finalizada")
TASK_FIELDS = ("color", "arrival", "duration", "period", "deadline", "events")


# Um retrato completo da simulação em um instante de tempo.
class simulation_state:
    def __init__(self, algorithm, processors_list, tasks_to_arrival, result):
        self.tick = 0
        self.algorithm = algorithm
        self.processors_list = processors_list
        self.tasks_to_arrival = tasks_to_arrival
        self.ready_queue = []
        self.running_tasks = []
        self.suspended_tasks = []
        # Guarda todas as instâncias concluídas, inclusive por edição manual.
        self.terminated_tasks = []
        self.result = result
        self.log = ""
        self.random_state = random.getstate()
        # Eventos no limite de um tick são consumidos no próximo despacho,
        # antes de executar o intervalo que começa nesse mesmo instante.
        self.reschedule_needed = False

    def task_queues(self):
        return (("Nova", self.tasks_to_arrival), ("Pronta", self.ready_queue),
                ("Executando", self.running_tasks), ("Suspensa", self.suspended_tasks),
                ("Finalizada", self.terminated_tasks))

    def current_task(self, task_id):
        # O número da instância mantém a ordem de criação mesmo após editar o ingresso.
        active = [(task, name) for name, queue in self.task_queues() if name != "Finalizada"
                  for task in queue if task.id == task_id]
        if active:
            return min(active, key=lambda item: item[0].instance_number)
        completed = [task for task in self.terminated_tasks if task.id == task_id]
        if completed:
            return max(completed, key=lambda task: task.instance_number), "Finalizada"
        raise ValueError(f"A tarefa {task_id} não existe no estado atual.")

    @property
    def is_finished(self):
        return not (self.tasks_to_arrival or self.ready_queue or self.running_tasks
                    or self.suspended_tasks)

    @property
    def is_blocked(self):
        # Suspensão manual não possui um instante de retomada automática.
        return bool(self.suspended_tasks and not
                    (self.tasks_to_arrival or self.ready_queue or self.running_tasks))

    def enqueue_next_instance(self, task):
        if task.instance_number >= SIMULATION_LIMIT:
            return None
        next_number = task.instance_number + 1
        # Uma perda de prazo pode já ter criado a próxima instância.
        if any(other.id == task.id and other.instance_number == next_number
               for _, queue in self.task_queues() for other in queue):
            return None
        next_instance = task.create_next_instance()
        self.tasks_to_arrival.append(next_instance)
        return next_instance

    def refresh_result(self):
        self.result.algorithm = self.algorithm
        self.result.num_cpus = len(self.processors_list)
        self.result.current_suspended = [(task.id, task.instance_number)
                                         for task in self.suspended_tasks]

    def edit(self, *, algorithm=None, num_cpus=None, task_id=None, changes=None, task_state=None):
        # A transação trabalha numa cópia. Erros nunca deixam filas/CPUs pela metade,
        # e os estados anteriores do histórico permanecem intocados.
        edited = deepcopy(self)
        descriptions = []
        if algorithm is not None:
            value = str(algorithm).strip().upper()
            if value not in ("RM", "EDF"):
                raise ValueError("Algoritmo inválido. Digite RM ou EDF.")
            edited.algorithm = value
            descriptions.append(f"algoritmo {value}")
        if num_cpus is not None:
            count = positive_integer(num_cpus, "Número de processadores")
            for cpu in edited.processors_list[count:]:
                if cpu.task_running is not None:
                    task = cpu.task_running
                    edited.running_tasks.remove(task)
                    task.processor = None
                    edited.ready_queue.append(task)
                    cpu.task_running = None
            edited.processors_list = edited.processors_list[:count]
            while len(edited.processors_list) < count:
                edited.processors_list.append(processor(len(edited.processors_list) + 1))
            descriptions.append(f"{count} processador(es)")
        if task_id is not None:
            edited._edit_task(task_id, changes or {}, task_state)
            descriptions.append(f"tarefa {task_id}")
        elif changes or task_state is not None:
            raise ValueError("Selecione uma tarefa antes de aplicar alterações.")
        edited.reschedule_needed |= self._edit_requires_rescheduling(edited)
        edited.refresh_result()
        if descriptions:
            edited.log += f"[Edição no instante {edited.tick}] " + ", ".join(descriptions) + ".\n"
        return edited

    def _edit_requires_rescheduling(self, edited):
        # Sem tarefas prontas não há alternativa a despachar ou a preemptar.
        # Cores, eventos do projeto B e alterações futuras não mudam a decisão.
        if not edited.ready_queue:
            return False
        if (self.algorithm != edited.algorithm
                or len(edited.processors_list) > len(self.processors_list)):
            return True

        def running_ids(state):
            return {(task.id, task.instance_number) for task in state.running_tasks}

        if running_ids(self) != running_ids(edited):
            return True

        def priorities(state):
            values = {}
            for task in state.ready_queue + state.running_tasks:
                primary = task.period if state.algorithm == "RM" else task.absolute_deadline
                values[(task.id, task.instance_number)] = (
                    primary, task.deadline, task.arrival, task.duration)
            return values

        before = priorities(self)
        after = priorities(edited)
        # Remover somente uma tarefa que já estava esperando não altera quem
        # executa; admitir/retomar uma candidata ou mudar sua prioridade pode alterar.
        return any(key not in before or value != before[key] for key, value in after.items())

    def _edit_task(self, task_id, changes, task_state):
        task, source = self.current_task(task_id)
        target = source
        if task_state is not None:
            target = next((name for name in TASK_STATES
                           if name.casefold() == str(task_state).strip().casefold()), None)
            if target is None:
                raise ValueError("Estado inválido. Escolha Nova, Pronta, Executando, Suspensa ou Finalizada.")
        values = validate_changes(task, changes)
        if source == "Finalizada" and target != "Finalizada":
            raise ValueError("Uma instância finalizada não pode ser reaberta. Retroceda a simulação para editá-la antes do término.")
        if values["arrival"] != task.arrival and source != "Nova":
            raise ValueError("O ingresso dessa instância já ocorreu. Retroceda até o estado Nova para alterá-lo.")
        if target == "Nova":
            if task.computational_time:
                raise ValueError("Uma instância que já executou não pode voltar a Nova. Retroceda a simulação.")
            if values["arrival"] < self.tick:
                raise ValueError("Uma tarefa Nova precisa ter ingresso no instante atual ou no futuro.")
        elif values["arrival"] > self.tick:
            raise ValueError("A tarefa ainda não chegou. Antecipe o ingresso enquanto ela estiver Nova ou avance o relógio.")

        # Características se aplicam às instâncias ainda não concluídas. Ingressos
        # já registrados e dados dos intervalos executados não são reescritos.
        siblings = [other for name, queue in self.task_queues() if name != "Finalizada"
                    for other in queue if other.id == task_id]
        if not siblings:
            siblings = [task]
        for other in siblings:
            finishing = other is task and target == "Finalizada"
            if (values["duration"] < other.computational_time
                    or (values["duration"] == other.computational_time and not finishing)):
                raise ValueError(f"A duração deve superar os {other.computational_time} ticks já executados pela instância {other.instance_number}, ou ser igual ao finalizar a instância.")
        for other in siblings:
            for key in ("color", "duration", "period", "deadline", "events"):
                setattr(other, key, deepcopy(values[key]))
            if other is task:
                other.arrival = values["arrival"]
            elif other in self.tasks_to_arrival:
                other.arrival = values["arrival"] + (other.instance_number - task.instance_number) * values["period"]
            other.end_period = other.arrival + other.period
            other.absolute_deadline = other.arrival + other.deadline
        info = next(info for info in self.result.tasks if info.id == task_id)
        for key in TASK_FIELDS:
            setattr(info, key, deepcopy(values[key]))

        if source == target:
            return
        free_cpu = None
        if target == "Executando":
            free_cpu = next((cpu for cpu in self.processors_list if cpu.task_running is None), None)
            if free_cpu is None:
                raise ValueError("Todos os processadores estão ocupados. Libere um processador ou aumente a quantidade antes de colocar a tarefa em execução.")
        for _, queue in self.task_queues():
            if task in queue:
                queue.remove(task)
        if task.processor is not None:
            task.processor.task_running = None
            task.processor = None

        if target == "Nova":
            # Desfaz uma admissão manual no próprio instante atual, sem tocar nos
            # intervalos anteriores e sem duplicar a chegada no próximo passo.
            self.result.events = [event for event in self.result.events
                                  if not (event.kind == "arrival" and event.tick == self.tick
                                          and event.task_id == task.id
                                          and event.instance == task.instance_number)]

        if target != "Nova":
            if not any(event.kind == "arrival" and event.task_id == task.id
                       and event.instance == task.instance_number for event in self.result.events):
                self.result.events.append(Event("arrival", self.tick, task.id, task.instance_number))
        queues = dict(self.task_queues())
        queues[target].append(task)
        if target == "Executando":
            task.processor = free_cpu
            free_cpu.task_running = task
        elif target == "Finalizada":
            self.result.events.append(Event("finish", self.tick, task.id, task.instance_number))
            if not task.is_late:
                self.enqueue_next_instance(task)


def positive_integer(value, name, minimum=1):
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError(f"{name} deve ser um número inteiro.") from None
    if number < minimum:
        raise ValueError(f"{name} deve ser maior ou igual a {minimum}.")
    return number


def validate_changes(task, changes):
    if any(key not in TASK_FIELDS for key in changes):
        raise ValueError("A edição contém um campo de tarefa desconhecido.")
    values = {key: deepcopy(changes.get(key, getattr(task, key))) for key in TASK_FIELDS}
    values["color"] = str(values["color"]).strip().removeprefix("#").upper()
    if not re.fullmatch(r"[0-9A-F]{6}", values["color"]):
        raise ValueError("Cor inválida. Use seis dígitos RGB hexadecimais, por exemplo FF0000.")
    for key, label in (("arrival", "Ingresso"), ("duration", "Duração"),
                       ("period", "Período"), ("deadline", "Prazo")):
        values[key] = positive_integer(values[key], label, 0 if key == "arrival" else 1)
    if values["period"] != values["deadline"]:
        raise ValueError("RM e EDF exigem prazo igual ao período. Altere os dois campos juntos.")
    if isinstance(values["events"], str):
        try:
            values["events"] = ast.literal_eval(values["events"].strip() or "[]")
        except (ValueError, SyntaxError):
            raise ValueError("Eventos devem ser uma lista de textos, por exemplo ['evento1'].") from None
    if not isinstance(values["events"], list) or any(not isinstance(item, str) for item in values["events"]):
        raise ValueError("Eventos devem ser uma lista de textos, por exemplo ['evento1'].")
    return values
