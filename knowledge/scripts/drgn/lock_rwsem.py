"""
RWSem 分析脚本 (优化版)
用法: 注入 lock_addr 后执行

优化:
1. 使用 frame.locals() 获取锁变量 (首选)
2. 栈搜索兜底
3. 检测任务正在等待的其他锁
"""
from drgn import Object, container_of
from drgn.helpers.linux.list import list_for_each_entry
from drgn.helpers.linux.pid import for_each_task

# lock_addr 由外部传入
addr = lock_addr
rwsem = Object(prog, "struct rw_semaphore", address=addr)

# ============ Phase 1: 解析锁状态 ============
print(f"## RWSem Analysis @ {hex(addr)}")
print()

owner_raw = rwsem.owner.value_()
owner_info = None
state = "Unknown"

if owner_raw == 0:
    state = "Unlocked"
elif owner_raw == 1:
    state = "Reader Held"
else:
    owner_task_addr = owner_raw & ~0x7
    if owner_task_addr:
        state = "Writer Held"
        try:
            owner_task = Object(prog, "struct task_struct", address=owner_task_addr)
            owner_pid = owner_task.pid.value_()
            owner_comm = owner_task.comm.string_().decode()
            owner_info = (owner_pid, owner_comm, hex(owner_task_addr))
        except:
            owner_info = ("?", "?", hex(owner_task_addr))

# 输出状态表格
print("| Field | Value |")
print("|:---|:---|")
print(f"| **State** | {state} |")
if owner_info:
    pid, comm, addr_hex = owner_info
    print(f"| **Owner** | [PID {pid}] {comm} (`{addr_hex}`) |")

# 解析 count
try:
    count_val = rwsem.count.counter.value_()
except:
    count_val = rwsem.count.value_()

count_unsigned = count_val & 0xffffffffffffffff
print(f"| **Count** | `{hex(count_unsigned)}` |")
print()

# ============ Phase 2: 从 wait_list 获取等待者 ============
waiter_tasks = set()
waiters = []
try:
    waiter_type = prog.type("struct rwsem_waiter")
    for waiter in list_for_each_entry(waiter_type, rwsem.wait_list.address_of_(), "list"):
        task = waiter.task
        waiter_tasks.add(int(task))
        
        pid = task.pid.value_()
        comm = task.comm.string_().decode()
        task_addr = hex(task.value_())
        try:
            t_state = task.state.value_()
        except:
            t_state = "?"
        
        wtype = "writer" if waiter.type.value_() == 0 else "reader"
        waiters.append((pid, comm, wtype, task_addr, t_state))
except Exception as e:
    print(f"> [!WARNING] Waiter parse error: {e}")

print(f"### Waiters ({len(waiters)})")
print()
if waiters:
    print("| PID | COMM | TYPE | Task Addr | State |")
    print("|:---|:---|:---|:---|:---|")
    for pid, comm, wtype, taddr, tstate in waiters:
        print(f"| {pid} | {comm} | {wtype} | `{taddr}` | {tstate} |")
else:
    print("(None)")
print()

# ============ Phase 3: 检测其他等锁情况 ============

def extract_lock_from_frame(frame):
    """尝试从帧中提取 lock 变量"""
    try:
        locals_list = frame.locals()
        for var_name in ['lock', 'sem', 'rwsem', 'l']:
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

# 检测读者持锁场景
if owner_raw == 1:
    suspect_readers = []
    path_associations = []
    lock_bytes = addr.to_bytes(8, 'little')
    
    lock_keywords = ["down_read", "down_write", "rwsem", "_raw_read", "_raw_write"]
    
    for task in for_each_task(prog):
        try:
            task_addr_int = int(task)
            if task_addr_int in waiter_tasks:
                continue
            
            trace = prog.stack_trace(task)
            frames = list(trace)
            
            # 计算栈边界 (进程栈或中断栈)
            try:
                thread_size = prog['THREAD_SIZE'].value_()
            except:
                thread_size = 16384  # 默认 16KB
            stack_base = task.stack.value_()
            stack_top = stack_base + thread_size
            
            # 检查栈上是否有目标锁地址
            has_target_lock = False
            for frame in frames:
                try:
                    sp = frame.sp
                    if stack_base <= sp < stack_top:
                        safe_size = min(stack_top - sp, 4096)
                    else:
                        safe_size = 512  # 中断栈等情况
                    
                    if safe_size <= 0:
                        continue
                    
                    data = prog.read(sp, safe_size)
                    if lock_bytes in data:
                        has_target_lock = True
                        break
                except:
                    pass
            
            if not has_target_lock:
                continue
            
            pid = task.pid.value_()
            comm = task.comm.string_().decode()
            
            # 检测是否在等待其他锁
            waiting_other = None
            for frame in frames:
                fname = frame.name or ""
                if any(x in fname for x in lock_keywords):
                    other_lock = extract_lock_from_frame(frame)
                    if other_lock and other_lock != addr:
                        waiting_other = other_lock
                        break
            
            stack_summary = get_stack_summary(trace)
            
            if waiting_other:
                path_associations.append({
                    'pid': pid, 'comm': comm,
                    'stack_has': addr, 'waiting_for': waiting_other,
                    'stack': stack_summary
                })
            else:
                found_frame = stack_summary[0] if stack_summary else "??"
                suspect_readers.append((pid, comm, found_frame))
        except:
            pass
    
    # 输出路径关联
    if path_associations:
        print("### 📍 Path Association (Target Lock in Stack, Waiting Other)")
        print()
        print("| PID | COMM | Stack Has | Waiting For | Stack Top |")
        print("|:---|:---|:---|:---|:---|")
        for t in path_associations:
            stack_str = " → ".join(t['stack'][:3])
            print(f"| {t['pid']} | {t['comm']} | `{hex(t['stack_has'])}` | `{hex(t['waiting_for'])}` | {stack_str} |")
        print()
    
    # 输出嫌疑读者
    if suspect_readers:
        print(f"### 📖 Suspect Readers ({len(suspect_readers)})")
        print()
        print("| PID | COMM | Frame |")
        print("|:---|:---|:---|")
        for pid, comm, frame in suspect_readers:
            print(f"| {pid} | {comm} | `{frame}` |")
