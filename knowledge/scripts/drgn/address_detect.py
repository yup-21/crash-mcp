"""
地址检测脚本
用于快速识别内核地址的类型和归属
用法: 注入 addr 变量后执行
"""
from drgn.helpers.linux.slab import slab_object_info
from drgn.helpers.common import identify_address

# addr 由外部传入
addr = addr

# Step 1: 符号查找 (最快)
try:
    sym = prog.symbol(addr)
    # binding: STB_GLOBAL, STB_LOCAL 等
    binding = str(sym.binding).replace("SymbolBinding.", "")
    sym_char = binding[0] if binding else "?"
    # 简单判断: 如果符号名以 "__ksymtab" 或 "_data" 结尾通常是数据
    is_func = not any(x in sym.name for x in ["_data", "ksymtab", "_bss", "_rodata"])
    print(f"SYMBOL:{sym.name}:{sym_char}:{is_func}")
except LookupError:
    # 不是符号，继续下一步
    try:
        info = slab_object_info(prog, addr)
        if info:
            cache_name = info.slab_cache.name.string_().decode()
            print(f"SLAB:{cache_name}:{info.allocated}")
        else:
            id_info = identify_address(prog, addr)
            if id_info:
                print(f"IDENTIFIED:{id_info}")
            else:
                print("UNKNOWN")
    except Exception as e:
        print(f"ERROR:{e}")
except Exception as e:
    print(f"ERROR:{e}")
