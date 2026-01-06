"""
结构体检查脚本
用于递归打印内核结构体内容
用法: 注入 struct_type, address, depth 变量后执行
"""
from drgn import TypeKind, Object

def print_struct(obj, depth=2, indent=0):
    """递归打印结构体"""
    prefix = "  " * indent
    lines = []
    
    try:
        type_kind = obj.type_.kind
        
        if type_kind in (TypeKind.STRUCT, TypeKind.UNION):
            lines.append(prefix + str(obj.type_.type_name()) + " {")
            for member in obj.type_.members:
                if member.name is None:
                    continue
                try:
                    member_obj = obj.member_(member.name)
                    # 计算成员地址
                    try:
                        member_addr = hex(obj.address_of_().value_() + member.offset // 8)
                    except:
                        member_addr = "N/A"
                        
                    # 检查是否是嵌套结构
                    if depth > 0 and member_obj.type_.kind in (TypeKind.STRUCT, TypeKind.UNION):
                        nested = print_struct(member_obj, depth-1, indent+1)
                        lines.append(prefix + "  [" + member_addr + "] " + member.name + " =")
                        lines.append(nested)
                    else:
                        try:
                            val = member_obj.value_()
                            if isinstance(val, int):
                                val = hex(val)
                            else:
                                val = str(val)
                        except:
                            val = str(member_obj)
                        lines.append(prefix + "  [" + member_addr + "] " + member.name + " = " + val)
                except Exception as e:
                    lines.append(prefix + "  " + member.name + " = <error: " + str(e) + ">")
            lines.append(prefix + "}")
        else:
            try:
                val = obj.value_()
                if isinstance(val, int):
                    val = hex(val)
                lines.append(prefix + str(val))
            except:
                lines.append(prefix + str(obj))
    except Exception as e:
        lines.append(prefix + "<error: " + str(e) + ">")
    
    return "\n".join(lines)

# 主入口
# 设置默认 depth 如果未定义
try:
    depth = depth
except NameError:
    depth = 2

obj = Object(prog, struct_type, address=address)
print(print_struct(obj, depth=depth))
