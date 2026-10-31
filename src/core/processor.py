"""CPU simulada: o vínculo com o TCB é preservado para evitar migração desnecessária."""

class processor:
  """CPU simulada com vínculo bidirecional ao TCB que ocupa o processador."""
  def __init__(self, id):
    """Inicializa os dados de processor com vínculos e valores próprios deste objeto."""
    self.id = id
    self.task_running = None

  def print(self):
    # Também pode ser chamado durante um intervalo OFF.
    """Emite o diagnóstico no log, sem depender da biblioteca gráfica."""
    print(f"CPU ID {self.id}:")
    print(f"  - Task running: {self.task_running.id if self.task_running else 'OFF'}")
 
