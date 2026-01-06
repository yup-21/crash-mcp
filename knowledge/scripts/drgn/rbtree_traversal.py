#!/usr/bin/env drgn
"""
红黑树遍历脚本
用于遍历 Linux 内核红黑树 (rb_root)
用法: 注入 root_val, target_type, member_name 变量后执行
"""
import json
import drgn
import traceback
from drgn.helpers.linux.rbtree import rbtree_inorder_for_each_entry

def get_head_ptr(prog, val, member_name):
    """
    Resolve rb_root pointer from a value, symbol, or address.
    """
    if isinstance(val, int):
        return drgn.Object(prog, 'struct rb_root', address=val)
    
    obj = val
    if isinstance(val, str):
        obj = prog[val]
        
    try:
        return getattr(obj, member_name).address_of_()
    except:
        pass
        
    try:
        if hasattr(obj, 'address_of_'):
            base_addr = obj.address_of_().value_()
        else:
            base_addr = obj.address_
            
        real_type = obj.type_
        while hasattr(real_type, 'type') and not hasattr(real_type, 'members'):
            real_type = real_type.type
            
        offset = None
        if hasattr(real_type, 'members'):
            for m in real_type.members:
                if m.name == member_name:
                    offset = m.offset // 8
                    break
        
        if offset is not None:
             target_addr = base_addr + offset
             return drgn.Object(prog, 'struct rb_root', address=target_addr).address_of_()
    except Exception as e:
        pass

    return getattr(obj, member_name)


nodes = []
try:
    if 'root_val' not in locals() and 'root_val' not in globals():
        pass 

    root_obj = get_head_ptr(prog, root_val, member_name)
    
    count = 0
    for node in rbtree_inorder_for_each_entry(target_type, root_obj, member_name):
        info = {}
        try:
            info['address'] = hex(node.address_of_())
        except:
            info['address'] = '?'
            
        try: info['name'] = node.name.string_().decode('utf-8', 'replace')
        except: pass
        try: info['comm'] = node.comm.string_().decode('utf-8', 'replace')
        except: pass
        try: info['pid'] = node.pid.value_()
        except: pass
        
        nodes.append(info)
        count += 1
        if count >= 100: break
        
except Exception as e:
    print(f"Error: {e}")
    traceback.print_exc()

print("JSON_START")
print(json.dumps(nodes, indent=2))
print("JSON_END")
