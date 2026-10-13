import os
import TCB
import extract_config
import choose_task

PATH_FILE = 'config_test.txt'
TICKS = 0
SIMULATION_LIMIT = 3

algorithm, quantum, num_cpus = extract_config.extract_system_parameters(PATH_FILE)

task_list = extract_config.extract_task_list(PATH_FILE)

print(f"algorithm {algorithm}")
print(f"quantum {quantum}")
print(f"num_cpus {num_cpus}")

for task in task_list:
    task.print()

#===========================

tasks_to_arrival = task_list
ready_queue = []
suspended_tasks = []
terminated_tasks = []


while len(terminated_tasks) != len(task_list):

    # arrival of tasks

    still_to_arrival = []

    for task in tasks_to_arrival:
        if task.arrival == TICKS:
            ready_queue.append(task)
            print(f"Task {task.id} has arrived at tick {TICKS}.")
        else:
            still_to_arrival.append(task)

    tasks_to_arrival = still_to_arrival


    # return of suspended tasks to ready queue if their period has elapsed

    still_suspended = []

    for task in suspended_tasks:
        if (TICKS - task.arrival) % task.period == 0:
            ready_queue.append(task)
            print(f"Task {task.id} has returned from suspended state at tick {TICKS}.")
        else:
            still_suspended.append(task)

    suspended_tasks = still_suspended



    task_chosen = choose_task.choose_task(ready_queue, algorithm)

    if not task_chosen:
        TICKS += 1
        print(f"No task is running at tick {TICKS} -> {TICKS + 1}. Processor is idle.")
        continue

    print(f"Task {task_chosen.id} is running at tick {TICKS} -> {TICKS + 1}.")
    task_chosen.is_running = True
    task_chosen.computational_time += 1

    if task_chosen.computational_time == task_chosen.duration:
        task_chosen.computational_time = 0
        task_chosen.is_running = False
        ready_queue.remove(task_chosen)
        task_chosen.times_executed += 1
        if task_chosen.times_executed == SIMULATION_LIMIT:
            terminated_tasks.append(task_chosen)
            print(f"Task {task_chosen.id} has executed {SIMULATION_LIMIT} times and has reached the simulation limit.")
        else:
            suspended_tasks.append(task_chosen)
            print(f"Task {task_chosen.id} has finished executing in this period({task_chosen.times_executed}). Is now suspended until the next period.")

    TICKS += 1

print(f"End of simulation at tick {TICKS}. All tasks have reached the simulation limit of {SIMULATION_LIMIT} executions.")
exit(0)