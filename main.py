import os
import TCB
import processor
from utils import initialize_processors, pair_cpus_tasks
from extract_config import extract_system_parameters, extract_task_list
from choose_task import choose_task

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PATH_FILE = os.path.join(BASE_DIR, 'config_test.txt')

# GET SYSTEM PARAMETERS AND TASK LIST FROM CONFIG FILE

algorithm, quantum, num_cpus = extract_system_parameters(PATH_FILE)

task_list = extract_task_list(PATH_FILE)

print(f"algorithm {algorithm}")
print(f"quantum {quantum}")
print(f"num_cpus {num_cpus}")

for task in task_list:
    task.print()
    if algorithm == "RM" and task.period != task.deadline:
        print(f"Task {task.id} has a period different from its deadline. This is not allowed in RM scheduling. Exiting simulation.")
        exit(1)

# INITIALIZE SIMULATION VARIABLES

TICKS = 0
SIMULATION_LIMIT = 3

tasks_to_arrival = task_list
ready_queue = []
running_tasks = []
evaluate_tasks = []
terminated_tasks = []

processors_list = initialize_processors(num_cpus)

# MAIN SCHEDULING SIMULATION LOOP

while len(terminated_tasks) != len(task_list):

    print(f"==================== TICK: {TICKS} ===================")

    # timeout verify
    for task in ready_queue:
        if task.absolute_deadline == TICKS:
            print(f"SCHEADULING ERROR: Task {task.id}({task.instance_number}) has not completed its execution within its deadline at tick {TICKS}.")
            task.is_late = True
            new_instance = task.create_next_instance()
            tasks_to_arrival.append(new_instance)


    # arrival of tasks

    still_to_arrival = []

    for task in tasks_to_arrival:
        if task.arrival == TICKS:
            ready_queue.append(task)
            print(f"Task {task.id}({task.instance_number}) has arrived at tick {TICKS}.")
        else:
            still_to_arrival.append(task)

    tasks_to_arrival = still_to_arrival

    # choose the num_cpus most prioritized tasks:
    evaluate_tasks = ready_queue + running_tasks
    running_tasks = []
    ready_queue =[]
    for i in range(num_cpus):
        task_chosen = choose_task(evaluate_tasks, algorithm)
        if task_chosen:
            evaluate_tasks.remove(task_chosen)
            running_tasks.append(task_chosen)

    # no chosen tasks go back to to ready_queue:
    ready_queue = evaluate_tasks
    evaluate_tasks = []

    # colocar as running_tasks nos processadores corretos:
    running_tasks, processors_list = pair_cpus_tasks(running_tasks, processors_list)

    for cpu in processors_list:
        if cpu.task_running == None:
            print(f"Processor: {cpu.id}: No task is running at tick {TICKS} -> {TICKS + 1}.")
            continue

        task_chosen = cpu.task_running
        print(f"Processor {cpu.id}: Task {task_chosen.id}({task_chosen.instance_number}) is running at tick {TICKS} -> {TICKS + 1}.")
        task_chosen.computational_time += 1

        if task_chosen.computational_time == task_chosen.duration:
            task_chosen.processor = None
            cpu.task_running = None
            running_tasks.remove(task_chosen)
            if task_chosen.instance_number == SIMULATION_LIMIT:
                terminated_tasks.append(task_chosen)
                print(f"Task {task_chosen.id}({task_chosen.instance_number}) has executed {SIMULATION_LIMIT} times and has reached the simulation limit at tick {TICKS} -> {TICKS + 1}.")
            elif task_chosen.is_late == False:
                new_instance = task_chosen.create_next_instance()
                tasks_to_arrival.append(new_instance)
                print(f"Task {task_chosen.id}({task_chosen.instance_number}) completed his computation_time at tick {TICKS} -> {TICKS + 1}. Enqueuing new instance to arrive at tick {new_instance.arrival}.")
                 
    TICKS += 1

print(f"End of simulation at tick {TICKS}. All tasks have reached the simulation limit of {SIMULATION_LIMIT} executions.")
exit(0)
