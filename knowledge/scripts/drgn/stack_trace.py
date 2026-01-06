import drgn
from drgn.helpers.linux.pid import find_task
from drgn.helpers.linux.percpu import per_cpu_ptr

# 注入参数 (支持多种参数名)
# pid 或 target_pid (int, optional)
# cpu 或 target_cpu (int, optional)
# detail_level (str): 'min', 'normal', 'max'

try:
    # 兼容多种参数名
    pid = pid if 'pid' in dir() else (target_pid if 'target_pid' in dir() else None)
    cpu = cpu if 'cpu' in dir() else (target_cpu if 'target_cpu' in dir() else None)
    level = detail_level if 'detail_level' in dir() else 'normal'

    task = None
    
    # 模式 1: 按 CPU 查找 Active Task
    if cpu is not None:
        if 'runqueues' in prog:
            runqueues = prog['runqueues']
            # 需要传入地址
            rq = per_cpu_ptr(runqueues.address_of_(), cpu)
            task = rq.curr
        else:
            print(f"ERROR: 'runqueues' not found, cannot trace CPU {cpu}")
            import sys
            sys.exit(0)
    # 模式 2: 按 PID 查找
    elif pid is not None:
        task = find_task(prog, pid)
        if not task:
            print(f"ERROR: Task {pid} not found")
            import sys
            sys.exit(0)

    if not task:
        print("ERROR: No task specified")
        import sys
        sys.exit(0)

    # 获取 PID (如果是从 CPU 获取的 task)
    pid_val = task.pid.value_()
    
    # Header info
    comm = task.comm.string_().decode('utf-8', 'replace')
    try: state = task.state.value_()
    except: state = "?"
    task_addr = hex(task.value_())
    cpu_val = task.cpu.value_() if hasattr(task, 'cpu') else "?"
    
    print(f"PID: {pid_val}  TASK: {task_addr}  CPU: {cpu_val}  COMMAND: \"{comm}\"")


    # ---------- Frame Processing ----------
    try:
        trace = drgn.stack_trace(task)
        frames = list(trace)
    except Exception as e:
        print(f"ERROR: Failed to unwind stack: {e}")
        frames = []
    
    # helper for slab info
    def get_slab_info(addr):
        try:
            import drgn.helpers.linux.slab as slab_helper
            info = slab_helper.slab_object_info(prog, addr)
            if info:
                # info.slab_cache is struct kmem_cache*
                try:
                    cache_name = info.slab_cache.name.string_().decode('utf-8', 'replace')
                except:
                    cache_name = "unknown_cache"
                return f"(Slab: {cache_name})"
        except:
            pass
        return ""

    for i, frame in enumerate(frames):
        name = frame.name if frame.name else "??"
        pc = frame.pc
        sp = frame.sp
        
        # Frame header
        # #X [SP] FUNC at PC
        print(f" #{i:<2} [{hex(sp)}] {name} at {hex(pc)}")


        # Dump stack content (bt -f / -FF)
        if level in ['normal', 'max']:
            stack_start = sp
            if i + 1 < len(frames):
                stack_end = frames[i+1].sp
            else:
                # Last frame, dump some bytes (e.g. 512)
                stack_end = stack_start + 512 
            
            # Limit scan size
            size = stack_end - stack_start
            if size > 4096: size = 4096 
            if size <= 0: continue

            try:
                content = prog.read(stack_start, size)
                
                for offset in range(0, size, 8):
                    curr_addr = stack_start + offset
                    if offset + 8 > len(content): break
                    val = int.from_bytes(content[offset:offset+8], 'little')
                    
                    info_str = ""
                    # 仅在 -FF (max) 模式下进行详细解析
                    if level == 'max':
                        # 1. 尝试解析为符号 (Text/Data)
                        try:
                            # 优先解析符号
                            sym = prog.symbol(val)
                            info_str = f"  [{sym.name}+{val - sym.address}]"
                        except:
                            # 2. 尝试解析为 Slab 对象 (失败则跳过)
                            slab_str = get_slab_info(val)
                            if slab_str:
                                info_str = f"  {slab_str}"
                    
                    # 格式: stack_addr: value  info
                    print(f"    {hex(curr_addr)}: {hex(val).ljust(18)}{info_str}")
                        
            except Exception as e:
                print(f"    (Stack read error: {e})")

except Exception as e:
    print(f"DRGN_ERROR:{e}")
