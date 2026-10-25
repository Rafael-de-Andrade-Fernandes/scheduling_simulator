import ast
import copy

class TCB:
  def __init__(self, task_line):
    self.id = int(task_line[0].strip())
    self.color = task_line[1].strip()
    self.arrival = int(task_line[2].strip())
    self.duration = int(task_line[3].strip())
    self.period = int(task_line[4].strip())
    self.deadline = int(task_line[5].strip())
    self.computational_time = 0 # quantum
    self.instance_number = 1
    self.end_period = self.arrival + self.period
    self.absolute_deadline = self.arrival + self.deadline
    self.processor = None
    self.is_late = False
    
    # Parse the events if the 7th parameter exists, otherwise default to an empty list
    if len(task_line) > 6 and task_line[6].strip():
        self.events = ast.literal_eval(task_line[6].strip())
    else:
        self.events = []

  def create_next_instance(self):
    next_instance = copy.deepcopy(self)
    next_instance.is_late = False
    next_instance.computational_time = 0
    next_instance.instance_number += 1
    next_instance.arrival = self.end_period
    next_instance.absolute_deadline = next_instance.arrival + next_instance.deadline
    next_instance.end_period = next_instance.arrival + next_instance.period
    return next_instance

  def print(self):
    print(f"Task ID {self.id}:")
    print(f"  - Color: {self.color}")
    print(f"  - Arrival: {self.arrival}")
    print(f"  - Duration: {self.duration}")
    print(f"  - Period: {self.period}")
    print(f"  - Deadline: {self.deadline}")
    print(f"  - Events: {self.events}")
    print(f"  - Computational Time: {self.computational_time}")
    print(f"  - Instance Number: {self.instance_number}")
    print(f"  - End Period: {self.end_period}")
    print(f"  - Absolute Deadline: {self.absolute_deadline}")
    print(f"  - Is Late: {self.is_late}")
 
