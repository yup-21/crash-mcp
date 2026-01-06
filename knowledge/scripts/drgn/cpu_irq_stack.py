"""
CPU IRQ 栈分析脚本
用于分析指定 CPU 的中断栈
用法: 注入 target_cpu 变量后执行
"""
import drgn
from drgn.helpers.linux.percpu import per_cpu_ptr
import sys

# 注入参数: target_cpu (int)
# 默认 CPU 0
cpu = target_cpu if 'target_cpu' in locals() or 'target_cpu' in globals() else 0

try:
    print(f"Analyzing IRQ Stack for CPU {cpu}...")

    addr = None
    size = 0
    
    # 策略 1: irq_stack_union (x86 commonly)
    if 'irq_stack_union' in prog:
        try:
            irq_stack_var = prog['irq_stack_union']
            irq_stack_ptr_val = per_cpu_ptr(irq_stack_var.address_of_(), cpu)
            addr = int(irq_stack_ptr_val)
            size = irq_stack_var.type_.size
            print("Found irq_stack_union")
        except Exception as e:
            print(f"Debug: irq_stack_union failed: {e}")

    # 策略 2: irq_stack_ptr (ARM64, etc)
    if not addr and 'irq_stack_ptr' in prog:
        try:
            stack_ptr = prog['irq_stack_ptr']
            # 注意: stack_ptr 是 per-cpu 变量, 类型可能是 unsigned long *
            # 我们需要读取这个变量的值
            val = per_cpu_ptr(stack_ptr.address_of_(), cpu) 
            # val现在指向 per-cpu 里的变量地址
            # 读取该处的值:
            stack_base = drgn.Object(prog, 'unsigned long', address=val).value_()
            if stack_base != 0:
                 addr = stack_base
                 size = 16384 # 16KB default
                 print("Found irq_stack_ptr")
        except Exception as e:
            print(f"Debug: irq_stack_ptr failed: {e}")

    # 策略 3: irq_stack (Direct array)
    if not addr and 'irq_stack' in prog:
        try:
            irq_stack = prog['irq_stack']
            # irq_stack 是 per-cpu 数组
            val = per_cpu_ptr(irq_stack.address_of_(), cpu)
            addr = int(val)
            size = irq_stack.type_.size
            print("Found irq_stack (array)")
        except Exception as e:
            print(f"Debug: irq_stack array failed: {e}")

    if not addr:
        print("Error: Could not locate IRQ stack address.")
        print("Checked: irq_stack_union, irq_stack_ptr, irq_stack")
        sys.exit(0)

    print(f"IRQ_STACK_ADDR: {hex(addr)}")
    print(f"IRQ_STACK_SIZE: {size}")
    
    # 2. Read content
    try:
        content = prog.read(addr, size)
    except Exception as e:
        print(f"Error reading stack memory at {hex(addr)}: {e}")
        print("Note: The requested memory might not be present in the vmcore.")
        sys.exit(0)
    
    # 3. Scan for symbols (Heuristic)
    print(f"Scanning stack for kernel text symbols...")
    print(f"{'SP':<18} {'VALUE':<18} {'SYMBOL'}")
    print("-" * 60)
    
    found_count = 0
    # Scan aligned 8-bytes
    for offset in range(0, size, 8):
        val_bytes = content[offset:offset+8]
        val = int.from_bytes(val_bytes, 'little')
        
        # Simple heuristic filter
        if val > 0xffffffff80000000 or val > 0xffff000000000000: 
            try:
                sym = prog.symbol(val)
                if sym:
                    # Filter out common noise if needed
                    current_sp = addr + offset
                    offset_str = f"{sym.name}+{val - sym.address}"
                    print(f"{hex(current_sp):<18} {hex(val):<18} <{offset_str}>")
                    found_count += 1
            except:
                pass
                
    if found_count == 0:
        print("No return addresses found.")

except SystemExit:
    pass
except Exception as e:
    print(f"Drgn Error: {e}")
