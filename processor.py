import ast
import TCB

class processor:
  def __init__(self, id):
    self.id = id
    self.task_running = None

  def print(self):
    print(f"CPU ID {self.id}:")
    print(f"  - Task running: {self.task_running.id}")
 
