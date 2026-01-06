#!/usr/bin/env drgn
"""
Drgn script to analyze memory usage.
Usage: drgn -c vmcore -s vmlinux memory.py

兼容多种内核版本的内存统计获取方式。
"""

from drgn.helpers.linux.pid import for_each_task

def get_memory_info(prog):
    """Get basic memory info."""
    print("## Memory Information")
    print()
    
    page_size = 4096  # 默认页大小
    try:
        page_size = prog["PAGE_SIZE"].value_()
    except:
        pass
    
    # 方法1: 尝试 vm_stat (某些内核)
    try:
        vm_stat = prog["vm_stat"]
        nr_free = vm_stat[prog["NR_FREE_PAGES"]].counter.value_()
        print(f"Free pages: {nr_free} ({nr_free * page_size // 1024 // 1024} MB)")
        return
    except:
        pass
    
    # 方法2: 尝试 vm_zone_stat (较新内核)
    try:
        from drgn.helpers.linux.mm import for_each_online_node
        vm_zone_stat = prog["vm_zone_stat"]
        nr_free = vm_zone_stat[prog["NR_FREE_PAGES"]].counter.value_()
        print(f"Free pages: {nr_free} ({nr_free * page_size // 1024 // 1024} MB)")
        return
    except:
        pass
    
    # 方法3: 遍历 zone 统计
    try:
        from drgn.helpers.linux.mm import for_each_zone
        total_free = 0
        for zone in for_each_zone(prog):
            try:
                free = zone.free_area[0].nr_free.value_()
                for i in range(1, 11):
                    free += zone.free_area[i].nr_free.value_() * (1 << i)
                total_free += free
            except:
                pass
        if total_free > 0:
            print(f"Free pages (from zones): {total_free} ({total_free * page_size // 1024 // 1024} MB)")
            return
    except:
        pass
    
    # 方法4: 从 meminfo 获取
    try:
        si_meminfo = prog["si_swapinfo"]  # 如果存在
        print("(Memory stats via alternative method)")
    except:
        print("(Could not get memory stats - kernel may not export required symbols)")
    
    # Get total memory
    try:
        if "_totalram_pages" in prog:
            totalram = prog["_totalram_pages"].value_()
        elif "totalram_pages" in prog:
            totalram = prog["totalram_pages"].value_()
        else:
            totalram = 0
            
        if totalram:
            print(f"Total RAM pages: {totalram} ({totalram * page_size // 1024 // 1024 // 1024} GB)")
    except:
        pass


def find_top_memory_tasks(prog, top_n=10):
    """Find tasks using the most memory."""
    print()
    print(f"## Top {top_n} Memory Users")
    print()
    
    tasks = []
    
    for task in for_each_task(prog):
        try:
            if not task.mm.value_():
                continue
            mm = task.mm
            
            # 尝试不同的 RSS 获取方式
            rss = 0
            try:
                # 新内核: rss_stat.count[].counter
                rss = mm.rss_stat.count[0].counter.value_()  # MM_FILEPAGES
                rss += mm.rss_stat.count[1].counter.value_()  # MM_ANONPAGES
            except:
                try:
                    # 某些内核: rss_stat.count[] 直接是 atomic_long_t
                    rss = mm.rss_stat.count[0].value_() + mm.rss_stat.count[1].value_()
                except:
                    try:
                        # 更老: _file_rss + _anon_rss
                        rss = mm._file_rss.counter.value_() + mm._anon_rss.counter.value_()
                    except:
                        continue
            
            tasks.append({
                'pid': task.pid.value_(),
                'comm': task.comm.string_().decode('utf-8', 'replace'),
                'rss': rss
            })
        except:
            pass
    
    tasks.sort(key=lambda x: x['rss'], reverse=True)
    
    print("| PID | COMM | RSS (pages) | RSS (MB) |")
    print("|:----|:-----|------------:|---------:|")
    for t in tasks[:top_n]:
        rss_mb = t['rss'] * 4 // 1024
        print(f"| {t['pid']} | {t['comm']} | {t['rss']} | {rss_mb} |")


# 主入口
get_memory_info(prog)
find_top_memory_tasks(prog)
