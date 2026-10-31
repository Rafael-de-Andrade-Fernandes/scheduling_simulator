"""Validação segura de campos do arquivo e unicidade das definições."""
import ast
import re


def validate_events_field(events_str, line_idx):
    """Valida uma lista de textos por literal seguro, sem executar seus conteúdos."""
    if not events_str:
        return True

    try:
        parsed_events = ast.literal_eval(events_str)
    except (ValueError, SyntaxError):
        print(f"Warning: Line {line_idx} ignored. "
              "The events list is poorly formatted (e.g., use ['event1', 'event2']).")
        return False

    if not isinstance(parsed_events, list):
        print(f"Warning: Line {line_idx} ignored. Events must be formatted as a list.")
        return False

    for item in parsed_events:
        if not isinstance(item, str):
            print(f"Warning: Line {line_idx} ignored. All events inside the list must be strings.")
            return False

    return True


def task_is_valid(task_line, i, seen_ids=None, seen_colors=None):
    """Verifica campos, identificadores e cores antes de aceitar uma definição."""
    line_idx = i + 1

    # 1. Checagem de quantidade de colunas
    if len(task_line) not in (6, 7):
        print(f"Warning: Line {line_idx} doesn't have the correct number of parameters. Invalid format.")
        return False

    # Remove espacos em branco das extremidades de todos os campos de uma so vez
    fields = [field.strip() for field in task_line]
    t_id_str, t_color, t_arr_str, t_dur_str, t_per_str, t_dl_str = fields[:6]

    # 2. Conversão e validação dos campos inteiros
    try:
        t_id = int(t_id_str)
        t_arrival = int(t_arr_str)
        t_duration = int(t_dur_str)
        t_period = int(t_per_str)
        t_deadline = int(t_dl_str)
    except ValueError:
        print(f"Warning: Line {line_idx} has invalid numeric parameters. "
              "All numeric parameters must be valid integers.")
        return False

    # Regras de limite: id, duration e deadline > 0; arrival e period >= 0
    if t_id <= 0 or t_duration <= 0 or t_deadline <= 0 or t_arrival < 0 or t_period < 0:
        print(f"Warning: Line {line_idx} has invalid numeric parameters. "
              "id, duration and deadline must be > 0; arrival and period must be >= 0.")
        return False

    # task_validation.py:58-61
    if seen_ids is not None:
        if t_id in seen_ids:
            print(f"Warning: Line {line_idx} ignored. Task ID {t_id} is duplicated.")
            return False
        seen_ids.add(t_id)

    # 3. Validação da cor em hexadecimal (6 caracteres)
    if not re.match(r'^[0-9a-fA-F]{6}$', t_color):
        print(f"Warning: Line {line_idx} ignored. Color '{t_color}' is not a valid hex format.")
        return False

    # Aperiódicas serão ignoradas: não reservam uma cor das tarefas simuladas.
    if seen_colors is not None and t_period > 0:
        normalized_color = t_color.upper()
        if normalized_color in seen_colors:
            print(f"Error: Line {line_idx}: color {normalized_color} is already used by another task.")
            return False
        seen_colors.add(normalized_color)

    # 4. Validação do campo opcional de eventos (se fornecido)
    if len(fields) == 7:
        events_str = fields[6]
        if not validate_events_field(events_str, line_idx):
            return False

    return True
