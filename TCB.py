import ast

class TCB:
  def __init__(self, task_line):
    self.id = int(task_line[0].strip())
    self.color = task_line[1].strip()
    self.arrival = int(task_line[2].strip())
    self.duration = int(task_line[3].strip())
    self.period = int(task_line[4].strip())
    self.deadline = int(task_line[5].strip())
    self.computational_time = 0
    self.instance_number = 1
    self.end_period = self.arrival + self.period
    self.is_running = False
    
    # Parse the events if the 7th parameter exists, otherwise default to an empty list
    if len(task_line) > 6 and task_line[6].strip():
        self.events = ast.literal_eval(task_line[6].strip())
    else:
        self.events = []


  def create_new_instance_of(task)
    new_instance = task
    new_instance.computational_time = 0
    new_instance.instance_number += 1
    new_instance.arrival = task.end_period
    new_instance.end_period = new_instance.arrival + new_instance.end_period
    

  def print(self):
    print(f"Task ID {self.id}:")
    print(f"  - Color: {self.color}")
    print(f"  - Arrival: {self.arrival}")
    print(f"  - Duration: {self.duration}")
    print(f"  - Period: {self.period}")
    print(f"  - Deadline: {self.deadline}")
    print(f"  - Events: {self.events}")
    print(f"  - Is Running: {self.is_running}")
    print(f"  - Computational Time: {self.computational_time}")
    print(f"  - Instance Number: {self.instance_number}")
    print(f"  - End Period: {self.end_period}")
 
