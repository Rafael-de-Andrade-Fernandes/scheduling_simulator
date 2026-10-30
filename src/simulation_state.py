import os
import TCB
import processor

class simulation_state
    def __init__():
        self.processors_list = []
        self.tasks_to_arrival = []
        self.ready_queue = []
        self.running_tasks = []
        self.terminated_tasks = []


    def set_state(PARAMETERS):
       

        return next_instance

    def __str__(self):
        return (
            f"Task ID {self.id}:\n"
            f"  - Color: {self.color}\n"
            f"  - Arrival: {self.arrival}\n"
            f"  - Duration: {self.duration}\n"
            f"  - Period: {self.period}\n"
            f"  - Deadline: {self.deadline}\n"
            f"  - Events: {self.events}\n"
            f"  - Computational Time: {self.computational_time}\n"
            f"  - Instance Number: {self.instance_number}\n"
            f"  - End Period: {self.end_period}\n"
            f"  - Absolute Deadline: {self.absolute_deadline}\n"
            f"  - Is Late: {self.is_late}"
        )

    def print(self):
        print(self)