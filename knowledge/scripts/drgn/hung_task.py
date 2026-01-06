#!/usr/bin/env drgn
"""
Drgn script to analyze hung tasks (D state).
用于分析长时间阻塞的任务。
"""

from drgn import Object
from drgn.helpers.linux.sched import task_state_to_char
from drgn.helpers.linux.pid import for_each_task

def find_hung_tasks(prog):
    """Find tasks in TASK_UNINTERRUPTIBLE (D) state."""
    
    hung_tasks = []
    
    for task in for_each_task(prog):
        try:
            # 获取状态字符
            state_char = task_state_to_char(task)
            
            # 只关注 D 状态 (TASK_UNINTERRUPTIBLE)
            if state_char != 'D':
                continue
            
            pid = task.pid.value_()
            comm = task.comm.string_().decode('utf-8', 'replace')
            
            # 尝试获取等待通道
            wchan = "?"
            try:
                if hasattr(task, 'last_wakee'):
                    pass  # 可以添加更多信息
            except:
                pass
            
            hung_tasks.append({
                'pid': pid,
                'comm': comm,
                'state': state_char,
            })
        except:
            pass
    
    return hung_tasks


def get_task_stack_summary(prog, task, max_frames=5):
    """Get short stack summary for a task."""
    try:
        trace = prog.stack_trace(task)
        frames = []
        for i, frame in enumerate(trace):
            if i >= max_frames:
                break
            name = frame.name or "??"
            # 跳过通用调度帧
            if name in ['__schedule', 'schedule', 'context_switch', '__switch_to']:
                continue
            frames.append(name)
        return " → ".join(frames[:3]) if frames else "(no frames)"
    except:
        return "(stack error)"


print("## Hung Task Analysis (D State)")
print()

hung = find_hung_tasks(prog)
print(f"Found **{len(hung)}** tasks in D (UNINTERRUPTIBLE) state:")
print()

if hung:
    print("| PID | COMM | Stack Top |")
    print("|:----|:-----|:----------|")
    
    from drgn.helpers.linux.pid import find_task
    for t in hung[:20]:  # Limit to first 20
        task = find_task(prog, t['pid'])
        stack = get_task_stack_summary(prog, task) if task else "(not found)"
        print(f"| {t['pid']} | {t['comm']} | {stack} |")
    
    if len(hung) > 20:
        print(f"\n... and {len(hung) - 20} more")
else:
    print("No hung tasks found.")
