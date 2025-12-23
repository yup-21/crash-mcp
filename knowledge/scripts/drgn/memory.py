#!/usr/bin/env drgn
"""
Drgn script to analyze memory usage.
Usage: drgn -c vmcore -s vmlinux memory.py
"""

from drgn.helpers.linux.mm import for_each_page

def get_memory_info(prog):
    """Get basic memory info."""
    print("=== Memory Information ===")
    
    # Try to get meminfo
    try:
        vm_stat = prog["vm_stat"]
        page_size = prog["PAGE_SIZE"].value_()
        
        nr_free = vm_stat[prog["NR_FREE_PAGES"]].counter.value_()
        print(f"Free pages: {nr_free} ({nr_free * page_size // 1024 // 1024} MB)")
        
        if "NR_ACTIVE_ANON" in [s.name for s in prog.type("enum zone_stat_item").enumerators]:
            nr_active_anon = vm_stat[prog["NR_ACTIVE_ANON"]].counter.value_()
            print(f"Active anon: {nr_active_anon} ({nr_active_anon * page_size // 1024 // 1024} MB)")
    except Exception as e:
        print(f"Could not get vm_stat: {e}")
    
    # Get total memory
    try:
        totalram = prog["_totalram_pages"].value_() if "_totalram_pages" in prog else 0
        if totalram:
            print(f"Total RAM pages: {totalram} ({totalram * 4096 // 1024 // 1024 // 1024} GB)")
    except:
        pass


def find_top_memory_tasks(prog, top_n=10):
    """Find tasks using the most memory."""
    from drgn.helpers.linux.list import list_for_each_entry
    
    print(f"\n=== Top {top_n} Memory Users ===")
    
    tasks = []
    init_task = prog["init_task"]
    
    for task in list_for_each_entry("struct task_struct",
                                     init_task.tasks.address_of_(),
                                     "tasks"):
        if task.mm.value_():
            mm = task.mm
            try:
                rss = mm.rss_stat.count[0].value_()  # MM_FILEPAGES
                rss += mm.rss_stat.count[1].value_()  # MM_ANONPAGES
                tasks.append({
                    'pid': task.pid.value_(),
                    'comm': task.comm.string_().decode(),
                    'rss': rss
                })
            except:
                pass
    
    tasks.sort(key=lambda x: x['rss'], reverse=True)
    
    for t in tasks[:top_n]:
        print(f"  PID {t['pid']:6}: {t['comm']:16} RSS={t['rss']} pages ({t['rss'] * 4 // 1024} MB)")


if __name__ == "__main__":
    get_memory_info(prog)
    find_top_memory_tasks(prog)
