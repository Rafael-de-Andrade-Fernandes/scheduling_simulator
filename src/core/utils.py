"""Associação entre TCBs e CPUs preservando afinidade e eliminando vínculos obsoletos."""
import processor


def initialize_processors(num_cpus):
    """Cria IDs estáveis de 1 a N para manter a afinidade dos processadores."""
    processors = []
    for i in range(num_cpus):
        cpu = processor.processor(i + 1)
        processors.append(cpu)
    return processors


def find_cpu_with_task(processors, task):
    """Localiza a alocação existente para não migrar uma tarefa sem necessidade."""
    for cpu in processors:
        if cpu.task_running == task:
            return cpu
    return None


def find_free_cpu(processors, running_tasks):
    """Libera um vínculo obsoleto de preempção e encontra capacidade disponível."""
    for cpu in processors:
        # CPU sem tarefa ou cuja tarefa anterior saiu de execucao
        if cpu.task_running is not None and cpu.task_running not in running_tasks:
            cpu.task_running = None
        if cpu.task_running is None or cpu.task_running not in running_tasks:
            return cpu
    return None


def pair_cpus_tasks(running_tasks, processors_list):
    """Preserva alocações válidas e ocupa somente CPUs necessárias às novas executantes."""
    for task in running_tasks:
        # 1. Verifica se a tarefa ja esta alocada em alguma CPU
        cpu_allocated = find_cpu_with_task(processors_list, task)
        if cpu_allocated is not None:
            continue

        # 2. Se nao estiver, busca uma CPU disponivel
        free_cpu = find_free_cpu(processors_list, running_tasks)
        if free_cpu is not None:
            free_cpu.task_running = task
            task.processor = free_cpu

    return running_tasks, processors_list
