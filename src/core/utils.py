"""Associação entre TCBs e CPUs preservando afinidade e eliminando vínculos obsoletos."""
from processor import processor


def initialize_processors(num_cpus):
    return [processor(index) for index in range(1, num_cpus + 1)]


def find_cpu_with_task(processors, task):
    for cpu in processors:
        if cpu.task_running == task:
            return cpu
    return None


def find_free_cpu(processors, running_tasks):
    for cpu in processors:
        if cpu.task_running is not None and cpu.task_running not in running_tasks:
            cpu.task_running = None
        if cpu.task_running is None:
            return cpu
    return None


def pair_cpus_tasks(running_tasks, processors_list):
    """Mantém a afinidade de quem continua executando e aloca apenas as novas executantes."""
    for task in running_tasks:
        cpu_allocated = find_cpu_with_task(processors_list, task)
        if cpu_allocated is not None:
            continue

        free_cpu = find_free_cpu(processors_list, running_tasks)
        if free_cpu is not None:
            free_cpu.task_running = task
            task.processor = free_cpu

    return running_tasks, processors_list
