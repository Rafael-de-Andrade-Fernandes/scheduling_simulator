import os
import TCB
from task_validation import task_is_valid
from choose_task import SCHEDULERS

# Valores padrão usados quando a primeira linha do arquivo não informa o parâmetro
DEFAULT_ALGORITHM = 'RM'
DEFAULT_QUANTUM = 1
DEFAULT_NUM_CPUS = 1

def get_valid_lines(file_path):
    if not os.path.exists(file_path):
        print(f"Error: The file '{file_path}' was not found.")
        exit(1)
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            lines = file.readlines()
            
        valid_lines = [line.strip() for line in lines if line.strip()]
        
        if len(valid_lines) < 2:
            print("Error: The file must contain at least two lines.")
            exit(1)

        return valid_lines
    
    except Exception as e:
        print(f"Error reading the file: {e}")
        exit(1)

def extract_system_parameters(file_path):

    valid_lines = get_valid_lines(file_path)

    system_line = valid_lines[0].rstrip(';').split(';')

    if len(system_line) > 3:
        print("Error: The first line is poorly formatted.")
        exit(1)

    # Parâmetros que faltam na primeira linha recebem o valor padrão (item 3.2 do PDF)
    while len(system_line) < 3:
        system_line.append("")

    algorithm = system_line[0].strip().upper()
    if algorithm == "":
        algorithm = DEFAULT_ALGORITHM
        print(f"Notice: algorithm not informed. Using the default: {DEFAULT_ALGORITHM}.")
    if algorithm not in SCHEDULERS:
        print(f"Error: Unsupported scheduling algorithm '{algorithm}'. Must be one of: {', '.join(sorted(SCHEDULERS.keys()))}.")
        exit(1)

    quantum_str = system_line[1].strip()
    num_cpus_str = system_line[2].strip()
    if quantum_str == "":
        quantum_str = str(DEFAULT_QUANTUM)
        print(f"Notice: quantum not informed. Using the default: {DEFAULT_QUANTUM}.")
    if num_cpus_str == "":
        num_cpus_str = str(DEFAULT_NUM_CPUS)
        print(f"Notice: number of CPUs not informed. Using the default: {DEFAULT_NUM_CPUS}.")

    # Validation for System Parameters
    try:
        quantum = int(quantum_str)
        if quantum < 1:
            print("Error: Quantum must be at least 1.")
            exit(1)
        num_cpus = int(num_cpus_str)
        if num_cpus < 1:
            print("Error: Number of CPUs must be at least 1.")
            exit(1)
    except ValueError:
        print("Error: All the parameters must be integers.")
        exit(1)

    print("=== SYSTEM PARAMETERS ===")
    print(f"Scheduling Algorithm: {algorithm}")
    print(f"Quantum: {quantum}")
    print(f"Number of CPUs: {num_cpus}\n")

    return algorithm, quantum, num_cpus
    

def extract_task_list(file_path):
    
    valid_lines = get_valid_lines(file_path)    

    task_list = []
    seen_ids = set()

    print("=== TASK LIST ===")
    for i in range(1, len(valid_lines)):
        task_line = valid_lines[i].rstrip(';').split(';')
        if task_is_valid(task_line, i, seen_ids):
            task = TCB.TCB(task_line)
            if task.period == 0:
                print(f"Warning: Line {i+1} ignored. Task ID {task.id} is aperiodic (period=0) and not supported yet.")
                continue
            task_list.append(task)
            task.print()
        else:
            print(f"Error: Invalid parameters in line {i+1}.")
            exit(1)

    # Sem tarefas periódicas não há o que simular (as aperiódicas foram ignoradas)
    if len(task_list) == 0:
        print("Error: No periodic tasks to simulate. Aperiodic tasks (period=0) are not supported yet.")
        exit(1)

    return task_list
