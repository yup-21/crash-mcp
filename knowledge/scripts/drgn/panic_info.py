"""
Panic 信息提取脚本
提取崩溃时的关键信息
"""
import drgn

print("## Panic Information")
print()

try:
    # 1. 获取崩溃线程
    try:
        crashed = prog.crashed_thread()
        if crashed:
            print(f"**Crashed Thread:** PID {crashed.pid.value_()} ({crashed.comm.string_().decode()})")
            print()
    except Exception as e:
        pass
    
    # 2. 尝试获取 panic_cpu
    try:
        if 'panic_cpu' in prog:
            panic_cpu = prog['panic_cpu']
            cpu_val = panic_cpu.value_() if hasattr(panic_cpu, 'value_') else int(panic_cpu)
            if cpu_val >= 0:
                print(f"**Panic CPU:** {cpu_val}")
    except:
        pass
    
    # 3. 获取 panic 字符串
    try:
        if 'panic_cpu' in prog:
            # 尝试从 printk buffer 获取 panic 信息
            pass
    except:
        pass
    
    # 4. 获取崩溃调用栈
    print()
    print("### Crash Stack Trace")
    print()
    try:
        crashed = prog.crashed_thread()
        if crashed:
            # crashed 是 Thread 对象，需要获取其 task
            task = crashed.object
            trace = prog.stack_trace(task)
            for i, frame in enumerate(list(trace)[:15]):
                name = frame.name or "??"
                print(f" #{i:<2} {name} at {hex(frame.pc)}")
    except Exception as e:
        print(f"(Could not get stack trace: {e})")
    
    # 5. 检测 panic 类型
    print()
    print("### Panic Type Detection")
    print()
    
    # 检查是否有 watchdog 相关
    try:
        crashed = prog.crashed_thread()
        if crashed:
            task = crashed.object
            trace = prog.stack_trace(task)
            frames = [f.name or "" for f in trace]
            
            if any("watchdog" in f for f in frames):
                print("- **Type:** Hard Lockup (Watchdog)")
            elif any("panic" in f for f in frames):
                if any("nmi_panic" in f for f in frames):
                    print("- **Type:** NMI Panic")
                else:
                    print("- **Type:** Kernel Panic")
            elif any("oops" in f.lower() for f in frames):
                print("- **Type:** Oops")
            else:
                print("- **Type:** Unknown")
                
            # 关键函数
            for f in frames:
                if f and "spin_lock" in f:
                    print("- **Stuck at:** Spinlock contention")
                    break
                elif f and "mutex" in f:
                    print("- **Stuck at:** Mutex contention")
                    break
                elif f and "rwsem" in f:
                    print("- **Stuck at:** RW Semaphore contention")
                    break
    except:
        pass

except Exception as e:
    print(f"DRGN_ERROR: {e}")
