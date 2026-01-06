"""
Mutex 分析脚本 (优化版)
用法: 注入 lock_addr 后执行

优化:
1. 使用 frame.locals() 获取锁变量 (首选)
2. 栈搜索兜底
3. 检测 holder 的栈帧
4. 检测等待者正在等待的其他锁
"""
from drgn import Object, container_of
from drgn.helpers.linux.list import list_for_each_entry
from drgn.helpers.linux.pid import for_each_task

# lock_addr 由外部传入
addr = lock_addr
mutex = Object(prog, "struct mutex", address=addr)

# ============ Phase 1: 解析锁状态 ============
print(f"## Mutex Analysis @ {hex(addr)}")
print()

# 解析 owner
try:
    owner_raw = mutex.owner.counter.value_()
except:
    owner_raw = mutex.owner.value_()

owner_task_addr = owner_raw & ~0x7
flags = owner_raw & 0x7

# 状态表格
print("| Field | Value |")
print("|:---|:---|")

if owner_task_addr:
    try:
        owner_task = Object(prog, "struct task_struct", address=owner_task_addr)
        owner_pid = owner_task.pid.value_()
        owner_comm = owner_task.comm.string_().decode()
        print(f"| **State** | Locked |")
        print(f"| **Owner** | [PID {owner_pid}] {owner_comm} (`{hex(owner_task_addr)}`) |")
        
        # 获取 owner 的栈帧
        try:
            owner_trace = prog.stack_trace(owner_task)
            stack_top = " → ".join([f.name or "??" for f in list(owner_trace)[:3]])
            print(f"| **Owner Stack** | {stack_top} |")
        except:
            pass
    except:
        print(f"| **State** | Locked |")
        print(f"| **Owner** | ? (`{hex(owner_task_addr)}`) |")
else:
    print(f"| **State** | Unlocked |")
    print(f"| **Owner** | (None) |")

print(f"| **Flags** | `{hex(flags)}` |")
print()

# ============ Phase 2: 从 wait_list 获取等待者 ============

def extract_lock_from_frame(frame):
    """尝试从帧中提取 lock 变量"""
    try:
        locals_list = frame.locals()
        for var_name in ['lock', 'mutex', 'l']:
            if var_name in locals_list:
                lock_var = frame[var_name]
                type_str = str(lock_var.type_)
                if '*' in type_str:
                    return lock_var.value_()
                else:
                    return lock_var.address_of_().value_()
    except:
        pass
    return None

def get_stack_summary(trace, max_frames=5):
    return [frame.name or "??" for frame in list(trace)[:max_frames]]

waiters = []
path_associations = []
lock_keywords = ["mutex_lock", "__mutex", "_raw_spin"]

try:
    waiter_type = prog.type("struct mutex_waiter")
    for waiter in list_for_each_entry(waiter_type, mutex.wait_list.address_of_(), "list"):
        task = waiter.task
        pid = task.pid.value_()
        comm = task.comm.string_().decode()
        task_addr = hex(task.value_())
        
        # 检测是否在等待其他锁
        waiting_other = None
        try:
            trace = prog.stack_trace(task)
            frames = list(trace)
            for frame in frames:
                fname = frame.name or ""
                if any(x in fname for x in lock_keywords):
                    other_lock = extract_lock_from_frame(frame)
                    if other_lock and other_lock != addr:
                        waiting_other = other_lock
                        break
        except:
            pass
        
        if waiting_other:
            path_associations.append({
                'pid': pid, 'comm': comm,
                'stack_has': addr, 'waiting_for': waiting_other,
                'stack': get_stack_summary(trace) if 'trace' in dir() else []
            })
        else:
            waiters.append((pid, comm, task_addr))
except Exception as e:
    print(f"> [!WARNING] Waiter parse error: {e}")

# 输出等待者
print(f"### ⏳ Waiters ({len(waiters)})")
print()
if waiters:
    print("| PID | COMM | Task Addr |")
    print("|:---|:---|:---|")
    for pid, comm, task_addr in waiters:
        print(f"| {pid} | {comm} | `{task_addr}` |")
else:
    print("(None)")
print()

# 输出路径关联
if path_associations:
    print("### 📍 Path Association (In Wait List, But Waiting Other Lock)")
    print()
    print("| PID | COMM | Waiting For (Mutex) | Actually Waiting | Stack Top |")
    print("|:---|:---|:---|:---|:---|")
    for t in path_associations:
        stack_str = " → ".join(t.get('stack', [])[:3]) or "?"
        print(f"| {t['pid']} | {t['comm']} | `{hex(t['stack_has'])}` | `{hex(t['waiting_for'])}` | {stack_str} |")
