import pytest
import os
import sys
from crash_mcp.drgn_session import DrgnSession

# Path to our mock drgn script
MOCK_DRGN_PATH = os.path.join(os.path.dirname(__file__), 'mock_drgn.py')

@pytest.fixture
def drgn_session():
    # Set the binary path to our mock script
    # We use python3 to execute the mock script
    # But DrgnSession expects a binary path. 
    # We can use a wrapper or just point to the script if it's executable.
    # The mock script has #!/usr/bin/env python3 and we can make it executable,
    # or we can pass "python3 tests/mock_drgn.py" as the binary command if we adjust DrgnSession.
    # DrgnSession takes binary_path and splits args.
    
    # Simpler: Make mock_drgn.py executable or call it via python
    # Let's trust the shebang and set executable permission
    os.chmod(MOCK_DRGN_PATH, 0o755)
    
    session = DrgnSession(
        dump_path='/tmp/vmcore', 
        kernel_path='/tmp/vmlinux',
        binary_path=MOCK_DRGN_PATH
    )
    yield session
    session.close()

def test_start_session(drgn_session):
    drgn_session.start()
    assert drgn_session.is_active()

def test_execute_command(drgn_session):
    drgn_session.start()
    output = drgn_session.execute_command('prog')
    assert "CoreDump(prog, '/path/to/vmcore')" in output

def test_execute_command_assignment(drgn_session):
    drgn_session.start()
    # Assignment produces no output
    output = drgn_session.execute_command('task = find_task(prog, 1)')
    assert output == ""
    
    # Verify strict evaluation
    output = drgn_session.execute_command('task.comm')
    assert '"systemd"' in output

def test_close_session(drgn_session):
    drgn_session.start()
    drgn_session.close()
    assert not drgn_session.is_active()
