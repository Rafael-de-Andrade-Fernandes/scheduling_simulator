"""Leitura de texto configurável, diagnósticos e construção das definições periódicas."""
import os
import TCB
from task_validation import task_is_valid
from choose_task import normalize_algorithm

# Campos vazios do sistema usam os valores sugeridos pelo requisito 3.2.
DEFAULT_ALGORITHM = 'RM'
DEFAULT_QUANTUM = 1
DEFAULT_NUM_CPUS = 1

class ConfigError(ValueError):
    """Entrada inválida; o chamador decide se exibe o erro no console ou na janela."""


def get_valid_lines(file_path):
    if not os.path.exists(file_path):
        raise ConfigError(f"Error: The file '{file_path}' was not found.")
    try:
        # utf-8-sig aceita arquivos com ou sem o BOM comum em editores do Windows.
        with open(file_path, 'r', encoding='utf-8-sig') as file:
            lines = file.readlines()
    except (OSError, UnicodeError) as error:
        raise ConfigError(f"Error reading the file: {error}") from error

    valid_lines = [line.strip() for line in lines if line.strip()]
    if len(valid_lines) < 2:
        raise ConfigError("Error: The file must contain at least two lines.")
    return valid_lines


def extract_configuration(file_path, log):
    """Lê o arquivo uma vez, para que sistema e tarefas usem a mesma configuração."""
    valid_lines = get_valid_lines(file_path)
    parameters = _extract_system_parameters(valid_lines, log)
    tasks = _extract_task_list(valid_lines, log)
    return (*parameters, tasks)


# As extrações parciais preservam os pontos de entrada anteriores. O simulador
# usa extract_configuration para evitar duas leituras do mesmo arquivo.
def extract_system_parameters(file_path, log):
    return _extract_system_parameters(get_valid_lines(file_path), log)


def _extract_system_parameters(valid_lines, log):
    system_line = valid_lines[0].rstrip(';').split(';')
    if len(system_line) > 3:
        raise ConfigError("Error: The first line is poorly formatted.")

    while len(system_line) < 3:
        system_line.append("")

    algorithm_str = system_line[0].strip()
    if algorithm_str == "":
        algorithm_str = DEFAULT_ALGORITHM
        log.append(f"Notice: algorithm not informed. Using the default: {DEFAULT_ALGORITHM}.")
    try:
        algorithm = normalize_algorithm(algorithm_str)
    except ValueError as error:
        raise ConfigError(f"Error: {error}")

    quantum_str = system_line[1].strip()
    num_cpus_str = system_line[2].strip()
    if quantum_str == "":
        quantum_str = str(DEFAULT_QUANTUM)
        log.append(f"Notice: quantum not informed. Using the default: {DEFAULT_QUANTUM}.")
    if num_cpus_str == "":
        num_cpus_str = str(DEFAULT_NUM_CPUS)
        log.append(f"Notice: number of CPUs not informed. Using the default: {DEFAULT_NUM_CPUS}.")

    try:
        quantum = int(quantum_str)
        num_cpus = int(num_cpus_str)
    except ValueError:
        raise ConfigError("Error: All the parameters must be integers.")
    if quantum < 1:
        raise ConfigError("Error: Quantum must be at least 1.")
    if num_cpus < 1:
        raise ConfigError("Error: Number of CPUs must be at least 1.")

    log.append("=== SYSTEM PARAMETERS ===")
    log.append(f"Scheduling Algorithm: {algorithm}")
    log.append(f"Quantum: {quantum}")
    log.append(f"Number of CPUs: {num_cpus}\n")

    return algorithm, quantum, num_cpus


def extract_task_list(file_path, log):
    return _extract_task_list(get_valid_lines(file_path), log)


def _extract_task_list(valid_lines, log):
    task_list = []
    seen_ids = set()
    seen_colors = set()

    log.append("=== TASK LIST ===")
    for i, line in enumerate(valid_lines[1:], start=1):
        task_line = line.rstrip(';').split(';')
        if not task_is_valid(task_line, i, log, seen_ids, seen_colors):
            raise ConfigError(f"Error: Invalid parameters in line {i+1}.")

        task = TCB.TCB(task_line)
        task.color = task.color.upper()
        if task.period == 0:
            log.append(f"Warning: Line {i+1} ignored. Task ID {task.id} is aperiodic (period=0) and not supported yet.")
            continue
        task_list.append(task)
        log.append(str(task))

    if not task_list:
        raise ConfigError("Error: No periodic tasks to simulate. Aperiodic tasks (period=0) are not supported yet.")

    return task_list
