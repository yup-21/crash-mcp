# Linux Kernel Crash Analysis Methods

此文档包含了分析 Linux Kernel Crash 的标准方法和步骤。

---

## 方法: Hung Task 分析

**描述**: 分析任务长时间阻塞的原因。 识别 D 状态进程及其等待的资源。 

**适用场景/关键词**: INFO: task .* blocked for more than, hung_task_check, khungtaskd, blocked for more than

**分析步骤**:
1. **分析 D 状态任务，获取阻塞点**
   - 命令: `drgn:hung_task.py`
2. **查看所有任务状态**
   - 命令: `crash:ps -m`
3. **查找 UNINTERRUPTIBLE 状态任务**
   - 命令: `crash:ps | grep UN`
4. **查看阻塞任务堆栈**
   - 命令: `crash:bt <pid>`

**关键指标**:
- blocked_tasks (None)
- wait_channel (None)
- blocked_duration (None)

---

## 方法: 内存使用分析

**描述**: 分析系统内存使用情况。 识别内存消耗最大的进程和整体内存状态。 

**适用场景/关键词**: memory, vm_stat, rss, memory leak, low memory

**分析步骤**:
1. **获取内存统计和 Top 内存消耗者**
   - 命令: `drgn:memory.py`
2. **查看内核内存使用情况**
   - 命令: `crash:kmem -i`
3. **查看进程内存使用排序**
   - 命令: `crash:ps -m`

**关键指标**:
- free_memory (None)
- top_consumers (None)
- total_ram (None)

---

## 方法: Mutex 分析

**描述**: 分析互斥锁竞争和死锁。 识别锁持有者和等待者。 

**适用场景/关键词**: mutex, __mutex_lock, mutex_lock_slowpath, mutex_lock_killable, mutex_lock_interruptible

**分析步骤**:
1. **查找 D 状态进程，定位可能等待 mutex 的进程**
   - 命令: `crash:ps | grep UN`
2. **查看 D 状态进程堆栈，从 mutex_lock 参数获取锁地址**
   - 命令: `crash:bt <pid>`
3. **解析 mutex 结构体，获取 owner 和 wait_list**
   - 命令: `drgn:lock_mutex.py`
4. **查看持锁者堆栈**
   - 命令: `crash:bt <owner_pid>`

**关键指标**:
- owner_task (None)
- waiters (None)
- lock_state (None)

---

## 方法: 空指针解引用分析

**描述**: 分析空指针解引用导致的内核崩溃。 识别崩溃点和空指针变量。 

**适用场景/关键词**: NULL pointer dereference, unable to handle kernel NULL, BUG: unable to handle kernel paging request, Oops: 0000

**分析步骤**:
1. **查看崩溃堆栈**
   - 命令: `crash:bt`
2. **反汇编崩溃点**
   - 命令: `crash:dis -l <rip>`
3. **读取相关内存**
   - 命令: `crash:rd <addr>`

**关键指标**:
- crash_function (None)
- null_variable (None)
- rip (None)

---

## 方法: OOM Killer 分析

**描述**: 分析内存不足导致的 OOM 问题。 识别被杀进程和内存使用情况。 

**适用场景/关键词**: Out of memory, oom-kill, oom_reaper, Killed process, invoked oom-killer

**分析步骤**:
1. **查看 OOM 相关日志**
   - 命令: `crash:log | grep -i oom`
2. **查看内存使用情况**
   - 命令: `crash:kmem -i`
3. **查看进程内存使用**
   - 命令: `crash:ps -m`
4. **查看虚拟内存信息**
   - 命令: `crash:vm`

**关键指标**:
- killed_process (None)
- memory_usage (None)
- oom_score (None)

---

## 方法: Panic/Oops 信息分析

**描述**: 分析内核 Panic/Oops 信息。 提取 RIP、发生函数、崩溃原因等关键信息。 

**适用场景/关键词**: kernel panic, Oops, BUG:, RIP:, Unable to handle

**分析步骤**:
1. **获取崩溃时的调用栈**
   - 命令: `crash:bt`
2. **从日志提取 panic 上下文**
   - 命令: `crash:log | grep -A 30 'kernel panic\|Oops\|BUG:'`
3. **反汇编崩溃点指令**
   - 命令: `crash:dis -l <rip>`
4. **使用 drgn 提取结构化 panic 信息**
   - 命令: `drgn:panic_info.py`

**关键指标**:
- panic_type (None)
- rip (None)
- failing_function (None)
- cause (None)

---

## 方法: RW Semaphore 分析

**描述**: 分析读写信号量竞争和死锁。 支持识别持锁者、等待者和锁状态。 

**适用场景/关键词**: rwsem, rw_semaphore, down_read, down_write, rwsem_down_read_slowpath, rwsem_down_write_slowpath

**分析步骤**:
1. **查找 D 状态进程，定位可能等待 rwsem 的进程**
   - 命令: `crash:ps | grep UN`
2. **查看 D 状态进程堆栈，从 down_read/down_write 参数获取锁地址**
   - 命令: `crash:bt <pid>`
3. **解析 rwsem 结构体，获取 owner 和 wait_list**
   - 命令: `drgn:lock_rwsem.py`
4. **查看持锁者堆栈**
   - 命令: `crash:bt <owner_pid>`

**关键指标**:
- owner_task (None)
- waiter_count (None)
- lock_state (None)

---

## 方法: Slab 内存分析

**描述**: 分析 Slab 内存分配器状态。 用于排查内存泄漏、slab 耗尽等问题。 

**适用场景/关键词**: kmalloc, slab, kmem_cache, SLUB, kfree

**分析步骤**:
1. **显示 slab 缓存统计**
   - 命令: `crash:kmem -s`
2. **显示特定 slab 的详细信息**
   - 命令: `crash:kmem -S <slab_name>`
3. **使用 drgn 进行深度 slab 分析**
   - 命令: `drgn:slab_dump.py`

**关键指标**:
- slab_stats (None)
- top_consumers (None)
- leak_suspects (None)

---

## 方法: Soft Lockup 分析

**描述**: 分析 CPU 软死锁问题。 识别长时间占用 CPU 的任务。 

**适用场景/关键词**: soft lockup, softlockup, BUG: soft lockup, watchdog, rcu_sched detected stall

**分析步骤**:
1. **查看所有 CPU 堆栈**
   - 命令: `crash:bt -a`
2. **查看运行队列**
   - 命令: `crash:runq`
3. **查看所有任务堆栈**
   - 命令: `crash:foreach bt`

**关键指标**:
- locked_cpu (None)
- running_task (None)
- lock_time (None)

---

## 方法: Spinlock 分析

**描述**: 分析 Spinlock 锁状态、持有者和等待者。 支持锁依赖检测，识别持锁任务和等待锁的任务。 

**适用场景/关键词**: spin_lock, raw_spinlock, _raw_spin_lock, do_raw_spin_lock, queued_spin_lock

**分析步骤**:
1. **查看所有 CPU 堆栈，从 spin_lock 调用参数获取锁地址**
   - 命令: `crash:bt -a`
2. **从 panic 日志中查找可能的锁地址**
   - 命令: `crash:log | grep -E 'spin_lock|spinlock'`
3. **解析 spinlock 结构体，搜索栈中的锁引用，检测锁依赖**
   - 命令: `drgn:lock_spinlock.py`
4. **查看运行队列以确定哪个 CPU 可能持有锁**
   - 命令: `crash:runq`

**关键指标**:
- locked_val (None)
- holders (None)
- waiters (None)
- lock_deps (None)

---

## 方法: Stack Protector 分析

**描述**: 分析内核栈溢出/损坏问题。 识别导致栈损坏的函数。 

**适用场景/关键词**: stack-protector, Kernel stack is corrupted, __stack_chk_fail

**分析步骤**:
1. **查看崩溃堆栈**
   - 命令: `crash:bt`
2. **反汇编问题函数**
   - 命令: `crash:dis -l <function>`
3. **检查线程栈信息**
   - 命令: `crash:struct thread_info <addr>`

**关键指标**:
- corrupted_function (None)
- stack_overflow (None)
- canary_value (None)

---

## 方法: 调用栈分析

**描述**: 获取和分析进程调用栈。 识别阻塞点和锁等待。 

**适用场景/关键词**: backtrace, call trace, blocked, Call Trace

**分析步骤**:
1. **获取进程基础调用栈**
   - 命令: `crash:bt <pid>`
2. **获取带帧指针的详细调用栈**
   - 命令: `crash:bt -f <pid>`
3. **使用 drgn 获取带参数的调用栈**
   - 命令: `drgn:stack_trace.py`

**关键指标**:
- frames (None)
- blocked_at (None)
- lock_address (None)

---

## 方法: 任务列表分析

**描述**: 列出和过滤系统任务。 支持按状态和进程名过滤。 

**适用场景/关键词**: task, process, pid, ps

**分析步骤**:
1. **使用 drgn 遍历任务列表**
   - 命令: `drgn:task_list.py`
2. **查看所有进程**
   - 命令: `crash:ps`
3. **过滤 D 状态进程**
   - 命令: `crash:ps | grep UN`

**关键指标**:
- task_list (None)
- task_count (None)

