import drgn
from drgn.helpers.linux.pid import for_each_task

# 注入参数:
# state_char (str): 'D', 'R', 'S', 'Z'
# comm_filter (str): optional filter string

tasks = []
state_map = {'D': 2, 'R': 0, 'S': 1} # 2=TASK_UNINTERRUPTIBLE, 0=TASK_RUNNING, 1=TASK_INTERRUPTIBLE
target_state_val = state_map.get(state_char, -1)


print(f"{'PID':<8} {'COMM':<24} {'STATE':<5}")
print(f"{'-'*8} {'-'*24} {'-'*5}")

for task in for_each_task(prog):
    try:
        task_state = task.state.value_()
        
        # 简单状态过滤
        # 简单状态过滤
        if target_state_val != -1:
            if task_state != target_state_val:
                continue
        
        state_char_out = {v: k for k, v in state_map.items()}.get(task_state, str(task_state))
        
        pid = task.pid.value_()
        comm = task.comm.string_().decode('utf-8', 'replace')
        
        if comm_filter and comm_filter.lower() not in comm.lower():
            continue
        
        print(f"{pid:<8} {comm:<24} {state_char_out:<5}")
        tasks.append(pid)
    except:
        pass

