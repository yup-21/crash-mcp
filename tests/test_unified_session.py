import pytest
from unittest.mock import MagicMock, patch
from crash_mcp.unified_session import UnifiedSession
from crash_mcp.session import CrashSession
from crash_mcp.drgn_session import DrgnSession

@pytest.fixture
def unified_session():
    with patch('crash_mcp.session.pexpect.spawn'), \
         patch('crash_mcp.drgn_session.pexpect.spawn'):
        session = UnifiedSession('/tmp/vmcore', '/tmp/vmlinux')
        session.crash_session._process = MagicMock()
        session.crash_session._process.isalive.return_value = True
        session.drgn_session._process = MagicMock()
        session.drgn_session._process.isalive.return_value = True
        yield session

def test_routing_crash(unified_session):
    unified_session.crash_session.execute_command = MagicMock(return_value="crash_output")
    unified_session.drgn_session.execute_command = MagicMock(return_value="drgn_output")
    
    # Test 'sys' -> crash
    assert unified_session.execute_command("sys") == "crash_output"
    unified_session.crash_session.execute_command.assert_called_with("sys", 60, True)
    
    # Test 'bt' -> crash
    assert unified_session.execute_command("bt") == "crash_output"
    
def test_routing_drgn(unified_session):
    unified_session.crash_session.execute_command = MagicMock(return_value="crash_output")
    unified_session.drgn_session.execute_command = MagicMock(return_value="drgn_output")
    
    # Test 'prog' -> drgn
    assert unified_session.execute_command("prog") == "drgn_output"
    unified_session.drgn_session.execute_command.assert_called_with("prog", 60, True)
    
    # Test assignment -> drgn
    assert unified_session.execute_command("x = 1") == "drgn_output"
    
    # Test function call -> drgn
    assert unified_session.execute_command("find_task(1)") == "drgn_output"

def test_explicit_routing(unified_session):
    unified_session.crash_session.execute_command = MagicMock(return_value="crash_output")
    unified_session.drgn_session.execute_command = MagicMock(return_value="drgn_output")
    
    # Force crash
    assert unified_session.execute_command("crash: prog") == "crash_output"
    unified_session.crash_session.execute_command.assert_called_with("prog", 60, True)
    
    # Force drgn
    assert unified_session.execute_command("drgn: sys") == "drgn_output"
    unified_session.drgn_session.execute_command.assert_called_with("sys", 60, True)

@patch('crash_mcp.session.pexpect.spawn')
def test_remote_crash_init(mock_spawn):
    session = CrashSession('/tmp/vmcore', remote_host='example.com', remote_user='user')
    session.start()
    
    args, _ = mock_spawn.call_args
    cmd = args[0]
    cmd_args = args[1]
    
    assert cmd == 'ssh'
    assert 'user@example.com' in cmd_args
    assert '-t' in cmd_args
    assert any('crash' in arg for arg in cmd_args) 

@patch('crash_mcp.drgn_session.pexpect.spawn')
def test_remote_drgn_init(mock_spawn):
    session = DrgnSession('/tmp/vmcore', remote_host='192.168.1.1')
    session.start()
    
    args, _ = mock_spawn.call_args
    cmd = args[0]
    cmd_args = args[1]
    
    assert cmd == 'ssh'
    assert '192.168.1.1' in cmd_args
    assert '-t' in cmd_args
    # Verify drgn command is inside
    assert any('drgn' in arg for arg in cmd_args)
