import os
import TCB
import processor


def initialize_processors(num_cpus):
    processors_list = []
    for i in range(num_cpus):
        cpu = processor.processor(i+1)
        processors_list.append(cpu)
    return processors_list

def pair_cpus_tasks(running_tasks, processors_list):
    for task in running_tasks:
        first_cpu = None
        paired = False
        for cpu in reversed(processors_list):
            if cpu.task_running == task:
                paired = True
                break
            elif cpu.task_running not in running_tasks:
                first_cpu = cpu
        if  paired == False:
            first_cpu.task_running = task
            task.processor = first_cpu

    return running_tasks, processors_list