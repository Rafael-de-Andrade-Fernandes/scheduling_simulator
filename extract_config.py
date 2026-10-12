import os
import TCB
from task_validation import task_is_valid

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


def extract_system_parameters(file_path):

    valid_lines = get_valid_lines(file_path)

    system_line = valid_lines[0].rstrip(';').split(';')
    
    if len(system_line) != 3:
        print("Error: The first line is poorly formatted.")
        exit(1)
        
    algorithm = system_line[0].strip().upper() 
    quantum_str = system_line[1].strip()
    num_cpus_str = system_line[2].strip()
    
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

    print("=== TASK LIST ===")
    for i in range(1, len(valid_lines)):
        task_line = valid_lines[i].rstrip(';').split(';')
        if task_is_valid(task_line, i):
            task = TCB.TCB(task_line)
            if task.period == 0:
                print(f"Warning: Line {i+1} ignored. Task ID {task.id} is aperiodic (period=0) and not supported yet.")
                continue
            task_list.append(task)
            task.print()
        else:
            print(f"Error: Invalid parameters in line {i+1}.")
            exit(1)

    return task_list
