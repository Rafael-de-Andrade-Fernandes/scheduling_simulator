import os
import TCB
import processor
import simulation_state
from read_inputs import ler_setinha
from utils import initialize_processors, pair_cpus_tasks
from extract_config import extract_system_parameters, extract_task_list
from choose_task import choose_task

# main.py fica em src/, então subimos uma pasta para chegar na raiz do projeto
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH_FILE = os.path.join(BASE_DIR, 'configs', 'config_test.txt')

# GET SYSTEM PARAMETERS AND TASK LIST FROM CONFIG FILE

algorithm, quantum, num_cpus = extract_system_parameters(PATH_FILE)

task_list = extract_task_list(PATH_FILE)

print(f"algorithm {algorithm}")
print(f"quantum {quantum}")
print(f"num_cpus {num_cpus}")

for task in task_list:
    task.print()
    if task.period != task.deadline:
        print(f"Task {task.id} has a period different from its deadline. This is not allowed in RM or EDF scheduling. Exiting simulation.")
        exit(1)

# INITIALIZE SIMULATION VARIABLES

TICKS = 0
SIMULATION_LIMIT = 3

tasks_to_arrival = list(task_list)
ready_queue = []
running_tasks = []
terminated_tasks = []

state_list = []

processors_list = initialize_processors(num_cpus)

current_state = simulation_state.set_state(processors_list, tasks_to_arrival, ready_queue, running_tasks, terminated_tasks)
state_list.append(current_state)

# MAIN SCHEDULING SIMULATION LOOP

while len(current_state.terminated_tasks) != len(current_state.task_list):

    print(f"==================== TICK: {TICKS} ===================")

    # VISUALIZATION AND CONTROL AREA:
    acao = ler_setinha()
    
    if acao == 'DIREITA':
            TICKS += 1
            current_state = scale(current_state, TICKS)
            state_list.append(current_state)
            draw(current_state)
    elif acao == 'ESQUERDA':
        if TICKS > 0:
            TICKS -= 1 
            state_list.pop()
            draw(state_list[-1])
    elif acao == 'ESC':
        print("Program abort!\n")
        break

print(f"End of simulation at tick {TICKS}. All tasks have reached the simulation limit of {SIMULATION_LIMIT} executions.")
exit(0)

def scale(current_state, TICKS):

    tasks_to_arrival = current_state.tasks_to_arrival
    ready_queue = current_state.ready_queue
    running_tasks = current_state.running_tasks
    terminated_tasks = current_state.terminated_tasks

    processors_list = current_state.processors_list


    # timeout verify
    active_tasks = ready_queue + running_tasks

    for task in active_tasks:
        if task.absolute_deadline == TICKS:
            print(f"SCHEADULING ERROR: Task {task.id}({task.instance_number}) has not completed its execution within its deadline at tick {TICKS}.")
            task.is_late = True
            if task.instance_number < SIMULATION_LIMIT:
                new_instance = task.create_next_instance()
                tasks_to_arrival.append(new_instance)


    # arrival of tasks

    still_to_arrival = []

    for task in tasks_to_arrival:
        if task.arrival <= TICKS:
            ready_queue.append(task)
            print(f"Task {task.id}({task.instance_number}) has arrived at tick {TICKS}.")
        else:
            still_to_arrival.append(task)

    tasks_to_arrival = still_to_arrival

    # choose the num_cpus most prioritized tasks:
    candidates = ready_queue + running_tasks
    running_tasks = []
    
    for i in range(num_cpus):
        task_chosen = choose_task(candidates, algorithm)
        if task_chosen:
            candidates.remove(task_chosen)
            running_tasks.append(task_chosen)

    # no chosen tasks go back to to ready_queue:
    ready_queue = candidates
    for task in ready_queue:
        task.processor = None

    # colocar as running_tasks nos processadores corretos:
    running_tasks, processors_list = pair_cpus_tasks(running_tasks, processors_list)

    for cpu in processors_list:
        if cpu.task_running == None:
            print(f"Processor: {cpu.id}: No task is running at tick {TICKS} -> {TICKS + 1}.")
            continue

        task = cpu.task_running
        print(f"Processor {cpu.id}: Task {task.id}({task.instance_number}) is running at tick {TICKS} -> {TICKS + 1}.")
        task.computational_time += 1

        if task.computational_time == task.duration:
            task.processor = None
            cpu.task_running = None
            running_tasks.remove(task)
            if task.instance_number == SIMULATION_LIMIT:
                terminated_tasks.append(task)
                print(f"Task {task.id}({task.instance_number}) has executed {SIMULATION_LIMIT} times and has reached the simulation limit at tick {TICKS} -> {TICKS + 1}.")
            elif task.is_late == False:
                new_instance = task.create_next_instance()
                tasks_to_arrival.append(new_instance)
                print(f"Task {task.id}({task.instance_number}) completed his computation_time at tick {TICKS} -> {TICKS + 1}. Enqueuing new instance to arrive at tick {new_instance.arrival}.")
                 
    current_state = simulation_state.set_state(processors_list, tasks_to_arrival, ready_queue, running_tasks, terminated_tasks)
    return current_state


