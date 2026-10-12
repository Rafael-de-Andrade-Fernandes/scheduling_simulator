import os
import TCB
import extract_config

PATH_FILE = 'config_test.txt'


algorithm, quantum, num_cpus = extract_config.extract_system_parameters(PATH_FILE)

task_list = extract_config.extract_task_list(PATH_FILE)

print(f"algorithm {algorithm}")
print(f"quantum {quantum}")
print(f"num_cpus {num_cpus}")

for task in task_list:
    task.print()

    
