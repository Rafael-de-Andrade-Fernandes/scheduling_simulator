"""Conversão e validação dos campos editáveis de uma tarefa."""
import ast
import re
from copy import deepcopy

# Campos de uma tarefa que o usuário pode alterar (o ID não muda nunca)
TASK_FIELDS = ("color", "arrival", "duration", "period", "deadline", "events")


def positive_integer(value, name, minimum=1):
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError(f"{name} deve ser um número inteiro.") from None
    if number < minimum:
        raise ValueError(f"{name} deve ser maior ou igual a {minimum}.")
    return number


def validate_changes(task, changes):
    """Valida o conjunto completo de atributos sem modificar o TCB recebido."""
    if any(key not in TASK_FIELDS for key in changes):
        raise ValueError("A edição contém um campo de tarefa desconhecido.")
    # Eventos são mutáveis; a edição não pode compartilhar sua lista com o passado.
    values = {key: deepcopy(changes.get(key, getattr(task, key))) for key in TASK_FIELDS}

    values["color"] = str(values["color"]).strip().removeprefix("#").upper()
    if not re.fullmatch(r"[0-9A-F]{6}", values["color"]):
        raise ValueError("Cor inválida. Use seis dígitos RGB hexadecimais, por exemplo FF0000.")

    for key, label in (("arrival", "Ingresso"), ("duration", "Duração"),
                       ("period", "Período"), ("deadline", "Prazo")):
        values[key] = positive_integer(values[key], label, 0 if key == "arrival" else 1)

    if isinstance(values["events"], str):
        try:
            values["events"] = ast.literal_eval(values["events"].strip() or "[]")
        except (ValueError, SyntaxError):
            raise ValueError("Eventos devem ser uma lista de textos, por exemplo ['evento1'].") from None
    if not isinstance(values["events"], list) or any(not isinstance(item, str) for item in values["events"]):
        raise ValueError("Eventos devem ser uma lista de textos, por exemplo ['evento1'].")
    return values
