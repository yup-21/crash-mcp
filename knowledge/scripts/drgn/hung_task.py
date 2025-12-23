#!/usr/bin/env drgn
"""
Drgn script to analyze hung tasks.
Usage: drgn -c vmcore -s vmlinux hung_task.py
"""

from drgn import Object
from drgn.helpers.linux.sched import task_state_to_char
from drgn.helpers.linux.list import list_for_each_entry

def find_hung_tasks(prog, timeout_seconds=120):
    """Find tasks blocked longer than timeout_seconds."""
    import time
    
    hung_tasks = []
    init_task = prog["init_task"]
    
    for task in list_for_each_entry("struct task_struct", 
                                     init_task.tasks.address_of_(), 
                                     "tasks"):
        state = task.state.value_() if hasattr(task, 'state') else task.__state.value_()
        
        # Check if task is in TASK_UNINTERRUPTIBLE state
        if state & 2:  # TASK_UNINTERRUPTIBLE
            hung_tasks.append({
                'pid': task.pid.value_(),
                'comm': task.comm.string_().decode(),
                'state': task_state_to_char(task),
            })
    
    return hung_tasks


def print_task_stack(prog, pid):
    """Print stack trace for a task."""
    from drgn.helpers.linux.pid import find_task
    
    task = find_task(prog, pid)
    if task is None:
        print(f"Task {pid} not found")
        return
    
    print(f"Stack trace for {task.comm.string_().decode()} (pid={pid}):")
    print(prog.stack_trace(task))


if __name__ == "__main__":
    print("=== Hung Task Analysis ===")
    
    hung = find_hung_tasks(prog)
    print(f"Found {len(hung)} hung tasks:")
    
    for t in hung[:10]:  # Limit to first 10
        print(f"  PID {t['pid']}: {t['comm']} [{t['state']}]")
