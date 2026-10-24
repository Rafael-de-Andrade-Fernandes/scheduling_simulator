import os
import TCB
import random
def sort(object1, object2):
    return random.choice([object1, object2])


def choose_task(tasks, algorithm):
    if not tasks:
        return None
    
    task_chosen = tasks[0]

    if algorithm == 'RM':
        for task in tasks:
            if task.period < task_chosen.period:
                task_chosen = task
                # print(f"Task {task.id} chosen to run based on a shorter period.")
            elif task.period == task_chosen.period:
                if task.processor and not task_chosen.processor:
                    task_chosen = task
                    # print(f"Task {task.id} chosen to run because it is running.")
                elif (task.processor and task_chosen.processor) or (not task.processor and not task_chosen.processor):
                    if task.deadline < task_chosen.deadline:
                        task_chosen = task
                        # print(f"Task {task.id} chosen to run based on a shorter deadline.")
                    elif task.deadline == task_chosen.deadline:
                        if task.arrival < task_chosen.arrival:
                            task_chosen = task
                            # print(f"Task {task.id} chosen to run based on a shorter arrival time.")
                        elif task.arrival == task_chosen.arrival:
                            if task.duration < task_chosen.duration:
                                task_chosen = task
                                # print(f"Task {task.id} chosen to run based on a shorter duration.")
                            elif task.duration == task_chosen.duration:
                                task_chosen = sort(task_chosen, task)
                                # print(f"Task {task_chosen.id} chosen to run based on a sortition.")

        return task_chosen