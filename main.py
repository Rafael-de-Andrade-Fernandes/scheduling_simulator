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
    if algorithm == "RM" and task.period != task.deadline:
        print(f"Task {task.id} has a period different from its deadline. This is not allowed in RM scheduling. Exiting simulation.")
        exit(1)

#===========================

tasks_to_arrival = task_list
ready_queue = []
# running_tasks = []
# suspended_tasks = []
terminated_tasks = []

def create_next_instance(task):
    new_instance = task
    new_instance.arrival = task.end_period
    new_instance.computational_time = 0
    new_instance.end_period = new_instance.arrival + new_instance.period  # Update end_period for the new instance
    return new_instance

while len(terminated_tasks) != len(task_list):

    # arrival of tasks

    still_to_arrival = []

    for task in tasks_to_arrival:
        if task.arrival == TICKS:
            # task.period_completed = False  # task.period_completed == False in the inicialization
            # task.end_period = task.arrival + task.period  # task.end_period == task.arrival + task.period in the inicialization
            ready_queue.append(task)
            print(f"Task {task.id} has arrived at tick {TICKS}.")
        else:
            still_to_arrival.append(task)

    tasks_to_arrival = still_to_arrival


    # return of suspended tasks to ready queue if their period has elapsed

    #=========
    # still_suspended = []

    # for task in suspended_tasks:
    #     if task.end_period == TICKS:
    #         task.period_completed = False  # Reset for the next period
    #         task.end_period += task.period  # Update end_period for the next cycle
    #         ready_queue.append(task)
    #         print(f"Task {task.id} has returned from suspended state at tick {TICKS}.")
    #     else:
    #         still_suspended.append(task)

    # suspended_tasks = still_suspended
    #========

    # timeout verify
    for task in ready_queue:
        if task.end_period == TICKS:
            print(f"SCHEADULING ERROR: Task {task.id} has not completed its execution within its period at tick {TICKS}.")
            new_instance = task
            new_instance.computational_time = 0
            new_instance.arrival = task.end_period
            new_instance.end_period = new_instance.arrival + new_instance.period  # Update end_period for the new instance
            ready_queue.append(new_instance)
            task.is_late = True

    task_chosen = choose_task.choose_task(ready_queue, algorithm)

    if not task_chosen:
        TICKS += 1
        print(f"No task is running at tick {TICKS} -> {TICKS + 1}. Processor is idle.")
        continue

    print(f"Task {task_chosen.id} is running at tick {TICKS} -> {TICKS + 1}.")
    task_chosen.is_running = True
    task_chosen.computational_time += 1

    if task_chosen.computational_time == task_chosen.duration:

        task_chosen.period_completed = True
        task_chosen.computational_time = 0
        task_chosen.is_running = False
        ready_queue.remove(task_chosen)
        task_chosen.times_executed += 1
        if task_chosen.times_executed == SIMULATION_LIMIT:
            terminated_tasks.append(task_chosen)
            print(f"Task {task_chosen.id} has executed {SIMULATION_LIMIT} times and has reached the simulation limit.")
        else
            new_instance = create_next_instance(task)
            ready_queue.append(new_instance)
            
        # elif task_chosen.delay_counter > 0:
        #     print(f"Task {task_chosen.id} has completed its execution at tick {TICKS + 1}, but it was delayed by {task_chosen.delay_counter} period(s).")
        #     task_chosen.delay_counter -= 1
        #     ready_queue.append(task_chosen)
        # else:
        #     suspended_tasks.append(task_chosen)
        #     print(f"Task {task_chosen.id} has finished executing in this period({task_chosen.times_executed}). Is now suspended until the next period.")

    TICKS += 1

print(f"End of simulation at tick {TICKS}. All tasks have reached the simulation limit of {SIMULATION_LIMIT} executions.")
exit(0)
