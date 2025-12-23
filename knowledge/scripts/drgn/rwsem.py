#!/usr/bin/env drgn
"""
Drgn script to analyze rwsem (read-write semaphore).
Usage: drgn -c vmcore -s vmlinux rwsem.py <rwsem_addr>
"""

import sys
from drgn import Object, cast

def analyze_rwsem(prog, addr):
    """Analyze a rw_semaphore at the given address."""
    rwsem = Object(prog, "struct rw_semaphore", address=addr)
    
    print(f"=== RW Semaphore @ {hex(addr)} ===")
    
    # Get count/owner depending on kernel version
    if hasattr(rwsem, 'count'):
        count = rwsem.count.counter.value_()
        print(f"Count: {count}")
    
    if hasattr(rwsem, 'owner'):
        owner = rwsem.owner.value_()
        if owner:
            # Mask off flags
            owner_task_ptr = owner & ~0x7
            if owner_task_ptr:
                owner_task = Object(prog, "struct task_struct *", value=owner_task_ptr)
                print(f"Owner: {owner_task.comm.string_().decode()} (pid={owner_task.pid.value_()})")
            else:
                print("Owner: (reader-owned or none)")
        else:
            print("Owner: none")
    
    # Check wait list
    if hasattr(rwsem, 'wait_list'):
        wait_list = rwsem.wait_list
        if wait_list.next.value_() != wait_list.address_of_().value_():
            print("Wait list: non-empty")
            from drgn.helpers.linux.list import list_for_each_entry
            count = 0
            for waiter in list_for_each_entry("struct rwsem_waiter", 
                                              wait_list.address_of_(), 
                                              "list"):
                task = waiter.task
                print(f"  Waiter: {task.comm.string_().decode()} (pid={task.pid.value_()})")
                count += 1
                if count >= 10:
                    print("  ... (more waiters)")
                    break
        else:
            print("Wait list: empty")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: rwsem.py <rwsem_addr>")
        print("Example: rwsem.py 0xffff888123456789")
        sys.exit(1)
    
    addr = int(sys.argv[1], 16)
    analyze_rwsem(prog, addr)
