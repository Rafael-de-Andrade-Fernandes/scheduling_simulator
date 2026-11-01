"""CPU simulada: o vínculo com o TCB é preservado para evitar migração desnecessária."""

class processor:
    def __init__(self, id):
        self.id = id
        self.task_running = None
