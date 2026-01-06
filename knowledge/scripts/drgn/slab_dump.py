"""
Slab Cache 对象导出脚本
用法: 注入 cache_name 和 output_file 后执行

示例:
  cache_name = "task_struct"
  output_file = "/tmp/task_structs.txt"
  exec(open('slab_dump.py').read())
"""
from drgn.helpers.linux.slab import for_each_slab_cache, slab_cache_for_each_allocated_object

# 参数: cache_name, output_file (可选), struct_type (可选)
# cache_name: slab cache 名称 (支持部分匹配)
# output_file: 输出文件路径 (默认: /tmp/<cache_name>_objects.txt)
# struct_type: 结构体类型名 (默认: 从 cache_name 推断)

if 'cache_name' not in dir():
    print("Error: cache_name not set")
    print("Usage: cache_name = 'task_struct'; exec(...)")
    raise SystemExit(1)

# 默认输出文件
if 'output_file' not in dir():
    output_file = f"/tmp/{cache_name}_objects.txt"

# 默认结构体类型
if 'struct_type' not in dir():
    # 尝试推断
    struct_type = f"struct {cache_name}"

# 查找 slab cache
target_cache = None
for cache in for_each_slab_cache(prog):
    name = cache.name.string_().decode()
    if cache_name in name:
        target_cache = cache
        actual_name = name
        break

if not target_cache:
    print(f"Error: Slab cache '{cache_name}' not found")
    print("\nAvailable caches containing '{cache_name}':")
    for cache in for_each_slab_cache(prog):
        name = cache.name.string_().decode()
        if cache_name.lower() in name.lower():
            print(f"  - {name}")
    raise SystemExit(1)

print(f"## Slab Cache: {actual_name}")
print(f"  Object size: {target_cache.size.value_()} bytes")
print(f"  Output file: {output_file}")
print()

# 收集所有对象
objects = []
try:
    for obj in slab_cache_for_each_allocated_object(target_cache, struct_type):
        addr = int(obj)
        # 尝试获取有用信息
        info = ""
        try:
            # 通用字段探测
            if hasattr(obj, 'pid'):
                info = f"PID={obj.pid.value_()}"
            if hasattr(obj, 'comm'):
                info += f" COMM={obj.comm.string_().decode()}"
            if hasattr(obj, 'name'):
                n = obj.name
                if hasattr(n, 'string_'):
                    info = f"NAME={n.string_().decode()}"
                elif hasattr(n, 'name'):
                    info = f"NAME={n.name.string_().decode()}"
        except:
            pass
        objects.append((addr, info))
except Exception as e:
    print(f"Warning: Error iterating slab: {e}")
    print("Trying without type...")
    # 回退: 只获取地址
    try:
        for obj in slab_cache_for_each_allocated_object(target_cache, "void"):
            addr = int(obj)
            objects.append((addr, ""))
    except:
        pass

print(f"Found {len(objects)} objects")

# 写入文件
with open(output_file, 'w') as f:
    f.write(f"# Slab Cache: {actual_name}\n")
    f.write(f"# Object count: {len(objects)}\n")
    f.write(f"# Object size: {target_cache.size.value_()} bytes\n")
    f.write("#\n")
    f.write("# ADDRESS INFO\n")
    for addr, info in objects:
        f.write(f"{hex(addr)} {info}\n")

print(f"Saved to {output_file}")

# 显示前 10 个
print("\nFirst 10 objects:")
for i, (addr, info) in enumerate(objects[:10]):
    print(f"  [{i}] {hex(addr)} {info}")
if len(objects) > 10:
    print(f"  ... ({len(objects) - 10} more)")
