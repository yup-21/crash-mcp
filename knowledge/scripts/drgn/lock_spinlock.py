"""
Spinlock 分析脚本 (v3 - 锁依赖检测)
用法: 注入 lock_addr 后执行

特性:
1. 扫描所有任务
2. 解析 spin_lock 参数区分等待锁 vs 已持有锁
3. 检测并输出 A→B 锁依赖关系
4. 正确分类 holder vs waiter
"""
from drgn import Object
from drgn.helpers.linux.pid import for_each_task

# lock_addr 由外部传入
target_lock = lock_addr
target_lock_bytes = target_lock.to_bytes(8, 'little')

# ============ Phase 1: 解析锁状态 ============
print(f"## Spinlock Analysis @ {hex(target_lock)}")
print()

state = "Unknown"
val = 0

try:
    spinlock = Object(prog, "spinlock_t", address=target_lock)
    if hasattr(spinlock, "rlock"):
        raw_lock = spinlock.rlock.raw_lock
    else:
        raw_lock = spinlock.raw_lock
    
    if hasattr(raw_lock, "val"):
        val = raw_lock.val.counter.value_()
    elif hasattr(raw_lock, "locked"):
        val = raw_lock.locked.value_()
    else:
        val = int(raw_lock)
    
    state = "Locked" if val else "Unlocked"
except Exception as e:
    state = f"Parse Error: {e}"

print("| Field | Value |")
print("|:---|:---|")
print(f"| **State** | {state} |")
print(f"| **Raw Value** | `{hex(val)}` |")
print()

# ============ Phase 2: 扫描任务并检测锁依赖 ============

def extract_lock_from_frame(frame):
    """
    尝试从 spin_lock 帧中提取锁地址参数
    返回: lock_addr 或 None
    
    方法1: frame.locals() 获取调试符号 (首选)
    方法2: 启发式栈搜索 (兜底)
    """
    # 方法1: 通过 DWARF 调试信息获取 'lock' 变量
    try:
        locals_list = frame.locals()  # 返回字符串列表 ['lock', 'val', ...]
        if 'lock' in locals_list:
            lock_var = frame['lock']
            # lock_var 类型可能是:
            # - 指针 (struct qspinlock *) → 直接 value_() 获取地址
            # - 结构体 (struct qspinlock) → 需要 address_of_()
            type_str = str(lock_var.type_)
            if '*' in type_str:
                # 指针类型，直接获取值 (即地址)
                return lock_var.value_()
            else:
                # 结构体类型，获取地址
                return lock_var.address_of_().value_()
    except:
        pass
    
    # 方法1b: 尝试其他常见变量名
    try:
        for var_name in ['l', 'lck', 'spinlock']:
            if var_name in frame.locals():
                lock_var = frame[var_name]
                if hasattr(lock_var, 'address_of_'):
                    return lock_var.address_of_().value_()
                else:
                    return lock_var.value_()
    except:
        pass
    
    # 方法2: 启发式栈搜索 (兜底)
    try:
        sp = frame.sp
        # 尝试读取帧附近的指针 (x0/rdi 参数通常被保存在栈上)
        for offset in [0, 8, 16, 24, 32, 40, 48]:
            try:
                ptr_bytes = prog.read(sp + offset, 8)
                ptr_val = int.from_bytes(ptr_bytes, 'little')
                # 检查是否像内核地址
                if (ptr_val >> 48) in [0xffff, 0xfffe]:
                    # 验证是否是有效的 spinlock_t
                    try:
                        test_lock = Object(prog, "spinlock_t", address=ptr_val)
                        _ = test_lock.rlock if hasattr(test_lock, "rlock") else test_lock.raw_lock
                        return ptr_val
                    except:
                        pass
            except:
                pass
    except:
        pass
    
    return None

def get_stack_summary(trace, max_frames=3):
    """提取栈帧摘要，过滤 panic/crash 相关帧"""
    # 需要跳过的 panic/crash 相关帧
    skip_frames = {
        'crash_setup_regs', '__crash_kexec', 'panic', 'nmi_panic',
        'watchdog_hardlockup_check', 'sdei_watchdog_callback',
        'sdei_event_handler', '_sdei_handler', '__sdei_handler',
        '__sdei_asm_handler', 'crash_save_cpu', 'machine_kexec',
        '__cmpwait_case_4', '__cmpwait', 'arch_crash_save_vmcoreinfo',
    }
    
    frames = list(trace)
    result = []
    for frame in frames:
        name = frame.name or "??"
        if name not in skip_frames:
            result.append(name)
            if len(result) >= max_frames:
                break
    
    return result if result else [frames[0].name or "??" if frames else "??"]


# 收集结果
true_waiters = []       # 正在等待目标锁
holders_waiting = []    # 持有目标锁，等待其他锁
simple_holders = []     # 栈上有目标锁，但不在 spin_lock 中

for task in for_each_task(prog):
    try:
        pid = task.pid.value_()
        comm = task.comm.string_().decode()
        cpu = task.cpu.value_() if hasattr(task, "cpu") else -1
        on_cpu = task.on_cpu.value_() if hasattr(task, "on_cpu") else 0
        
        trace = prog.stack_trace(task)
        frames = list(trace)
        
        # 计算栈边界 (进程栈)
        try:
            thread_size = prog['THREAD_SIZE'].value_()
        except:
            thread_size = 16384  # 默认 16KB
        stack_base = task.stack.value_()
        stack_top = stack_base + thread_size
        
        # 获取 IRQ 栈边界 (如果任务在 CPU 上)
        irq_stack_base = 0
        irq_stack_top = 0
        if cpu >= 0 and on_cpu:
            try:
                from drgn.helpers.linux.percpu import per_cpu
                irq_ptr = per_cpu(prog['irq_stack_ptr'], cpu)
                if irq_ptr:
                    irq_stack_top = irq_ptr
                    irq_stack_base = irq_stack_top - 16384  # IRQ_STACK_SIZE
            except:
                pass
        
        # 检查栈是否包含目标锁地址
        has_target_lock = False
        for frame in frames:
            try:
                sp = frame.sp
                # 计算安全读取范围
                if stack_base <= sp < stack_top:
                    # 进程栈: 从 SP 到栈顶
                    safe_size = min(stack_top - sp, 4096)
                elif irq_stack_base and irq_stack_base <= sp < irq_stack_top:
                    # 中断栈: 从 SP 到 IRQ 栈顶
                    safe_size = min(irq_stack_top - sp, 4096)
                else:
                    # 未知栈，使用保守值
                    safe_size = 512
                
                if safe_size <= 0:
                    continue
                
                data = prog.read(sp, safe_size)
                if target_lock_bytes in data:
                    has_target_lock = True
                    break
            except:
                pass
        
        if not has_target_lock:
            continue
        
        # 分析所有锁等待帧 (spinlock + rwlock)
        lock_wait_frames = []
        lock_keywords = [
            "spin_lock", "_raw_spin", "queued_spin",  # spinlock
            "write_lock", "_raw_write", "queued_write",  # write lock
            "read_lock", "_raw_read", "queued_read",  # read lock
            "rwlock", "qrwlock"  # rwlock
        ]
        for frame in frames:
            fname = frame.name or ""
            if any(x in fname for x in lock_keywords):
                waiting_lock = extract_lock_from_frame(frame)
                lock_wait_frames.append({
                    'name': fname,
                    'waiting_lock': waiting_lock
                })
        
        stack_summary = get_stack_summary(trace)
        
        if not lock_wait_frames:
            # 不在 spin_lock 中，但栈上有目标锁 → 可能是 holder
            simple_holders.append({
                'pid': pid,
                'comm': comm,
                'cpu': cpu,
                'on_cpu': on_cpu,
                'stack': stack_summary
            })
            continue
        
        # 检查是在等待目标锁还是其他锁
        waiting_target = False
        waiting_other = None
        
        for sf in lock_wait_frames:
            if sf['waiting_lock'] == target_lock:
                waiting_target = True
            elif sf['waiting_lock']:
                waiting_other = sf['waiting_lock']
        
        if waiting_target:
            true_waiters.append({
                'pid': pid,
                'comm': comm,
                'cpu': cpu,
                'stack': stack_summary
            })
        elif waiting_other:
            # 持有目标锁，等待其他锁 → 锁依赖!
            holders_waiting.append({
                'pid': pid,
                'comm': comm,
                'cpu': cpu,
                'holds': target_lock,
                'waits': waiting_other,
                'stack': stack_summary
            })
        else:
            # spin_lock 中但无法确定等待哪个锁
            simple_holders.append({
                'pid': pid,
                'comm': comm,
                'cpu': cpu,
                'on_cpu': on_cpu,
                'stack': stack_summary,
                'note': 'in spin_lock (unknown target)'
            })
            
    except:
        pass

# ============ Phase 3: 输出结果 ============

# 路径关联 (栈上有目标锁，但当前等待其他锁)
if holders_waiting:
    print("### � Path Association (Target Lock in Stack, Waiting Other)")
    print()
    print("| PID | COMM | Stack Has | Waiting For | Stack Top |")
    print("|:---|:---|:---|:---|:---|")
    for t in holders_waiting:
        stack_str = " → ".join(t['stack'][:3])
        print(f"| {t['pid']} | {t['comm']} | `{hex(t['holds'])}` | `{hex(t['waits'])}` | {stack_str} |")
    print()
    print("> 💡 These tasks have target lock address in their stack (from call path) but are currently waiting for a **different lock**.")
    print()

# True Waiters
if true_waiters:
    print(f"### ⏳ True Waiters ({len(true_waiters)})")
    print()
    print("| PID | COMM | CPU | Stack Top |")
    print("|:---|:---|:---|:---|")
    for t in true_waiters:
        stack_str = " → ".join(t['stack'][:3])
        print(f"| {t['pid']} | {t['comm']} | {t['cpu']} | {stack_str} |")
    print()

# Simple Holders
if simple_holders:
    print(f"### 🔒 Suspect Holders ({len(simple_holders)})")
    print()
    print("| PID | COMM | CPU | On-CPU | Stack Top |")
    print("|:---|:---|:---|:---|:---|")
    for t in simple_holders:
        stack_str = " → ".join(t['stack'][:3])
        on_cpu_str = "✅" if t.get('on_cpu') else "❌"
        note = t.get('note', '')
        print(f"| {t['pid']} | {t['comm']} | {t['cpu']} | {on_cpu_str} | {stack_str} {note} |")
    print()

if not holders_waiting and not true_waiters and not simple_holders:
    print("(No tasks found with this lock address on stack)")
