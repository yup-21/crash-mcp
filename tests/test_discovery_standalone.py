import sys
import os
import unittest
import tempfile
import shutil

# Add src to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from crash_mcp.discovery import CrashDiscovery
from crash_mcp import server

class TestDiscovery(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_find_dumps(self):
        # Create dummy structure
        # /subdir/vmcore
        subdir = os.path.join(self.test_dir, "subdir")
        os.mkdir(subdir)
        
        vmcore_path = os.path.join(subdir, "vmcore")
        with open(vmcore_path, "w") as f:
            f.write("dummy dump content")
            
        dumps = CrashDiscovery.find_dumps([self.test_dir])
        self.assertEqual(len(dumps), 1)
        self.assertEqual(dumps[0]['filename'], "vmcore")
        self.assertEqual(dumps[0]['path'], vmcore_path)

    def test_match_kernel(self):
        # Create dummy dump and kernel
        dump_dir = os.path.join(self.test_dir, "dump_loc")
        os.mkdir(dump_dir)
        
        dump_path = os.path.join(dump_dir, "vmcore")
        with open(dump_path, "w") as f:
            f.write("content")
            
        kernel_path = os.path.join(dump_dir, "vmlinux-6.5.0")
        with open(kernel_path, "w") as f:
            f.write("kernel")
            
        # Should match local vmlinux
        match = CrashDiscovery.match_kernel(dump_path, [self.test_dir])
        self.assertEqual(match, kernel_path)

    def test_context_awareness(self):
        # Test that global context tracks the last session
        
        # Mocking sessions and last_session_id
        server.sessions = {}
        server.last_session_id = None
        
        # Create a mock session object
        class MockSession:
            def start(self): pass
            def execute_command(self, cmd, truncate=True): return f"executed {cmd}"
            def is_active(self): return True
            
        start_id = "test-session-id"
        server.sessions[start_id] = MockSession()
        server.last_session_id = start_id
        
        # Run command without session_id
        output = server.run_crash_command("sys")
        self.assertEqual(output, "executed sys")
        
    def test_list_limit(self):
        # Create 15 dummy dump files with different mtimes
        import time
        subdir = os.path.join(self.test_dir, "limit_test")
        os.mkdir(subdir)
        
        for i in range(15):
            p = os.path.join(subdir, f"core.{i}")
            with open(p, "w") as f: f.write(f"content {i}")
            # Ensure different timestamps
            t = time.time() - (15-i)*100 # newer files have larger i
            os.utime(p, (t, t))
            
        # Call server.list_crash_dumps directly (mocking config path)
        output = server.list_crash_dumps(subdir)
        self.assertIn("Found 15 crash dumps (showing top 10)", output)
        self.assertIn("... and 5 more.", output)
        # Should contain core.14 (newest) but not core.0 (oldest)
        self.assertIn("core.14", output)
        self.assertNotIn("core.0 ", output)

    def test_truncation(self):
        # Test input > 16KB
        from crash_mcp.session import CrashSession
        import pexpect
        
        # Mock pexpect process
        class MockProcess:
            def __init__(self):
                self.before = ""
            def sendline(self, cmd): pass
            def expect(self, pattern, timeout=None): pass
            def isalive(self): return True
        
        session = CrashSession("dump", "kernel")
        session._process = MockProcess()
        
    def test_truncation(self):
        # Test input > 16KB
        from crash_mcp.session import CrashSession
        import pexpect
        
        # Mock pexpect process
        class MockProcess:
            def __init__(self):
                self.before = ""
            def sendline(self, cmd): pass
            def expect(self, pattern, timeout=None): pass
            def isalive(self): return True
        
        session = CrashSession("dump", "kernel")
        session._process = MockProcess()
        
        # Create huge output (20KB)
        huge_output = "A" * 20000
        session._process.before = "cmd_echo\n" + huge_output
        session.PROMPT = "crash> "
        
        # 1. Test Default Truncation (Head+Tail)
        result = session.execute_command("cmd")
        self.assertTrue(len(result) < 20000)
        self.assertIn("[Output truncated by Crash MCP", result)
        # Should have approx 4KB head and 12KB tail
        self.assertTrue(result.startswith("AAAA"))
        self.assertTrue(result.endswith("AAAA"))
        
        # 2. Test Log Truncation (Tail-Only)
        session._process.before = "log\n" + ("B" * 20000) + "END"
        result_log = session.execute_command("log")
        self.assertTrue(len(result_log) < 20000)
        self.assertIn("[Log truncated (Head)", result_log)
        # Should end with END, but not start with B...B (start is cut)
        self.assertTrue(result_log.endswith("END"))
        self.assertFalse(result_log.startswith("BBBBBBBB"))
        
        # 3. Test Toggle (No Truncation)
        session._process.before = "cmd_echo\n" + huge_output
        result_full = session.execute_command("cmd", truncate=False)
        self.assertEqual(len(result_full), 20000)
        self.assertNotIn("truncated", result_full)

if __name__ == '__main__':
    unittest.main()

