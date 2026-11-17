"""Conversão e validação dos campos editáveis de uma tarefa."""
import ast
from copy import deepcopy
import re

# Campos de uma tarefa que o usuário pode alterar (o ID não muda nunca)
TASK_FIELDS = ("color", "arrival", "duration", "period", "deadline", "events")


# Confere e padroniza o identificador de uma tarefa: letras e números, sem espaços
# (ex.: "T1", "t30" ou "7"). Maiúsculas e minúsculas valem o mesmo, então vira maiúsculo.
# Identificador só de dígitos precisa ser maior que zero ("007" vira "7").
def normalize_task_id(value):
    text = str(value).strip().upper()
    if not re.fullmatch(r"[A-Z0-9]+", text):
        raise ValueError("Identificador inválido. Use letras e números, sem espaços (ex.: T1 ou 30).")
    if text.isdigit():
        if int(text) <= 0:
            raise ValueError("Identificador numérico deve ser maior que zero.")
        text = str(int(text))
    return text


# Converte um campo numérico e informa sua unidade/limite na mensagem de erro.
def positive_integer(value, name, minimum=1):
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError(f"{name} deve ser um número inteiro.") from None
    if number < minimum:
        raise ValueError(f"{name} deve ser maior ou igual a {minimum}.")
    return number


# Normaliza atributos de tarefas.
# Devolve um dicionário com todos os campos de TASK_FIELDS: os valores de "changes"
# onde existirem e os valores atuais da tarefa nos demais. Levanta ValueError se algo for inválido.
def validate_changes(task, changes):
    if any(key not in TASK_FIELDS for key in changes):
        raise ValueError("A edição contém um campo de tarefa desconhecido.")
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
