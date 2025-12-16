import pytest
import os
import sys
from crash_mcp.session import CrashSession

# Point to our mock crash script
MOCK_CRASH_PATH = os.path.join(os.path.dirname(__file__), 'mock_crash.py')

def test_session_start_and_command():
    # Use python to interpret the mock script to avoid shebang issues if any
    # But usually creating a wrapper or using the absolute path is fine.
    # We will use 'python3 path/to/mock_crash.py' as the command effectively? 
    # CrashSession expects a binary path. We can use a wrapper or just path to script if it is executable.
    
    # Let's ensure it is executable
    assert os.access(MOCK_CRASH_PATH, os.X_OK)

    session = CrashSession(
        dump_path="vmcore_dummy",
        kernel_path="vmlinux_dummy",
        binary_path=MOCK_CRASH_PATH
    )

    try:
        session.start(timeout=5)
        assert session.is_active()

        output = session.execute_command("sys")
        assert "KERNEL: /usr/lib/debug/lib/modules/6.5.0/vmlinux" in output
        assert "DUMPFILE: /var/crash/127.0.0.1-2023-10-10/vmcore" in output
        
        output2 = session.execute_command("bt")
        assert "mock output for: bt" in output2

    finally:
        session.close()
        assert not session.is_active()

def test_discovery_helper(tmp_path):
    from crash_mcp.discovery import CrashDiscovery
    
    d = tmp_path / "subdir"
    d.mkdir()
    p = d / "vmcore"
    p.write_text("content")
    
    dumps = CrashDiscovery.find_dumps([str(tmp_path)])
    assert len(dumps) == 1
    assert dumps[0]['filename'] == "vmcore"

    # Test KERNEL MATCHING (Same dir)
    k = d / "vmlinux-6.5.0"
    k.write_text("kernel")
    
    match = CrashDiscovery.match_kernel(str(p), [str(tmp_path)])
    print(f"Match result: {match}")
    assert match == str(k)
