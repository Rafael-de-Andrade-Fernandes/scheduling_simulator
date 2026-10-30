import os
import TCB
import processor

class simulation_state:
    def __init__(self):
        self.processors_list = []
        self.tasks_to_arrival = []
        self.ready_queue = []
        self.running_tasks = []
        self.terminated_tasks = []


    def set_state(self, processors_list, tasks_to_arrival, ready_queue, running_tasks, terminated_tasks):
        self.processors_list = processors_list
        self.tasks_to_arrival = tasks_to_arrival
        self.ready_queue = ready_queue
        self.running_tasks = running_tasks
        self.terminated_tasks = terminated_tasks

    def clear_state(self):
        self.processors_list = []
        self.tasks_to_arrival = []
        self.ready_queue = []
        self.running_tasks = []
        self.terminated_tasks = []
       