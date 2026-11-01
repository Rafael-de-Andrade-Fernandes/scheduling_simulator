"""Leitura de texto configurável, diagnósticos e construção das definições periódicas."""
import os
import TCB
from task_validation import task_is_valid
from choose_task import normalize_algorithm

# Valores padrão usados quando a primeira linha do arquivo não informa o parâmetro
DEFAULT_ALGORITHM = 'RM'
DEFAULT_QUANTUM = 1
DEFAULT_NUM_CPUS = 1

# Erro no arquivo de configuração. A mensagem diz o motivo do problema.
# (Levantar um erro é parecido com imprimir a mensagem e chamar exit() em C,
# mas quem chamou decide o que fazer: o terminal imprime, a janela mostra um aviso.)
class ConfigError(ValueError):
    pass


# Lê o arquivo e devolve as linhas que não estão em branco.
def get_valid_lines(file_path):
    if not os.path.exists(file_path):
        raise ConfigError(f"Error: The file '{file_path}' was not found.")
    try:
        with open(file_path, 'r', encoding='utf-8-sig') as file:
            lines = file.readlines()
    except Exception as e:
        raise ConfigError(f"Error reading the file: {e}")

    valid_lines = [line.strip() for line in lines if line.strip()]
    if len(valid_lines) < 2:
        raise ConfigError("Error: The file must contain at least two lines.")
    return valid_lines


# Lê algoritmo, quantum e CPUs da primeira linha, aplicando os valores padrão
# aos que faltam. Avisos são acrescentados ao log. Devolve (algoritmo, quantum, num_cpus).
def extract_system_parameters(file_path, log):
    valid_lines = get_valid_lines(file_path)

    system_line = valid_lines[0].rstrip(';').split(';')
    if len(system_line) > 3:
        raise ConfigError("Error: The first line is poorly formatted.")

    # Parâmetros que faltam na primeira linha recebem o valor padrão (item 3.2 do PDF)
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


# Lê as tarefas (da segunda linha em diante). Aperiódicas são ignoradas com um aviso.
# Devolve a lista de TCBs; avisos e erros de linha vão para o log.
def extract_task_list(file_path, log):
    valid_lines = get_valid_lines(file_path)

    task_list = []
    seen_ids = set()
    seen_colors = set()

    log.append("=== TASK LIST ===")
    for i in range(1, len(valid_lines)):
        task_line = valid_lines[i].rstrip(';').split(';')
        if not task_is_valid(task_line, i, log, seen_ids, seen_colors):
            raise ConfigError(f"Error: Invalid parameters in line {i+1}.")

        task = TCB.TCB(task_line)
        task.color = task.color.upper()
        if task.period == 0:
            log.append(f"Warning: Line {i+1} ignored. Task ID {task.id} is aperiodic (period=0) and not supported yet.")
            continue
        task_list.append(task)
        log.append(str(task))

    # Sem tarefas periódicas não há o que simular (as aperiódicas foram ignoradas)
    if len(task_list) == 0:
        raise ConfigError("Error: No periodic tasks to simulate. Aperiodic tasks (period=0) are not supported yet.")

    return task_list
