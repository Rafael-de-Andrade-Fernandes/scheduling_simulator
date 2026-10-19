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
    self.times_executed = 0
    self.end_period = self.arrival + self.period
    self.is_running = False
    self.is_suspended = False
    self.period_completed = False
    self.delay_counter = 0
    self.is_late = False
    
    # Parse the events if the 7th parameter exists, otherwise default to an empty list
    if len(task_line) > 6 and task_line[6].strip():
        self.events = ast.literal_eval(task_line[6].strip())
    else:
        self.events = []

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
    print(f"  - Times Executed: {self.times_executed}")
    print(f"  - Is Suspended: {self.is_suspended}")
    print(f"  - End Period: {self.end_period}")
    print(f"  - Is Late: {self.is_late}")
    print(f"  - Period Completed: {self.period_completed}\n")
