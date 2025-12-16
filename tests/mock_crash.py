#!/usr/bin/env python3
import sys
import time
import argparse

def main():
    # Simulate crash startup arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('args', nargs='*')
    args, unknown = parser.parse_known_args()

    # Verify we got a dump file (at least one arg)
    if not args.args:
        print("Usage: crash [System.map] [vmlinux] [dumpfile]")
        sys.exit(1)

    print("crash 8.0.2++")
    print("Copyright (C) 2002-2023  Red Hat, Inc. and others")
    print("...")
    print("      KERNEL: vmlinux")
    print("    DUMPFILE: " + args.args[-1])
    print("...")
    
    # Main loop
    while True:
        try:
            sys.stdout.write("crash> ")
            sys.stdout.flush()
            
            line = sys.stdin.readline()
            if not line:
                break
                
            cmd = line.strip()
            
            if cmd in ['q', 'quit', 'exit']:
                break
                
            if cmd == 'sys':
                print("      KERNEL: /usr/lib/debug/lib/modules/6.5.0/vmlinux")
                print("    DUMPFILE: /var/crash/127.0.0.1-2023-10-10/vmcore")
                print("        CPUS: 4")
                print("        DATE: Tue Oct 10 10:00:00 2023")
                print("      UPTIME: 00:01:00")
                print("LOAD AVERAGE: 0.00, 0.00, 0.00")
                print("       TASKS: 100")
                print("    NODENAME: localhost")
                print("     RELEASE: 6.5.0")
                print("     VERSION: #1 SMP PREEMPT_DYNAMIC Tue Oct 10 00:00:00 UTC 2023")
                print("     MACHINE: x86_64  (2000 Mhz)")
                print("      MEMORY: 8 GB")
            elif cmd:
                print(f"mock output for: {cmd}")
                
        except KeyboardInterrupt:
            break

if __name__ == "__main__":
    main()
