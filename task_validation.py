import os
import re
import ast

def task_is_valid(task_line, i):

    if len(task_line) != 6 and len(task_line) != 7:
        print(f"Warning: Line {i+1} doesn't have the correct number of parameters. Invalid format.")
        return False

    try:
        t_id = int(task_line[0].strip())
        t_arrival = int(task_line[2].strip())
        t_duration = int(task_line[3].strip())
        t_period = int(task_line[4].strip())
        t_deadline = int(task_line[5].strip())
    except ValueError:
        print(f"Warning: Line {i+1} has invalid numeric parameters. All numeric parameters must be valid integers.")
        return False

    if t_id <= 0 or t_duration <= 0 or t_period < 0 or t_deadline <= 0 or t_arrival < 0:
        print(f"Warning: Line {i+1} has invalid numeric parameters. Numeric parameters must be positive (arrival can be 0).")
        return False

    t_color = task_line[1].strip()
    if not re.match(r'^[0-9a-fA-F]{6}$', t_color):
        print(f"Warning: Line {i+1} ignored. Color '{t_color}' is not a valid hex format.")
        return False

    if len(task_line) == 7:
        events_str = task_line[6].strip()
        
        # Only validate if it's not empty
        if events_str:
            try:
                # Safely parse the string into a Python object
                parsed_events = ast.literal_eval(events_str)
                
                # Verify it is actually a list
                if not isinstance(parsed_events, list):
                    print(f"Warning: Line {i+1} ignored. Events must be formatted as a list.")
                    return False
                
                # Verify every item inside the list is a string
                if not all(isinstance(item, str) for item in parsed_events):
                    print(f"Warning: Line {i+1} ignored. All events inside the list must be strings.")
                    return False
                    
            except (ValueError, SyntaxError):
                print(f"Warning: Line {i+1} ignored. The events list is poorly formatted (e.g., use ['event1', 'event2']).")
                return False

    return True