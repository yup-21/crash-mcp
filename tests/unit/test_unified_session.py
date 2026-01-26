"""Test UnifiedSession command routing."""
import pytest
from unittest.mock import MagicMock, patch
from crash_mcp.common.unified_session import UnifiedSession


@pytest.fixture
def unified_session():
    """Create a UnifiedSession with mocked sub-sessions."""
    with patch('crash_mcp.crash.session.pexpect.spawn'), \
         patch('crash_mcp.drgn.session.pexpect.spawn'):
        session = UnifiedSession('/tmp/vmcore', '/tmp/vmlinux')
        session.crash_session._process = MagicMock()
        session.crash_session._process.isalive.return_value = True
        session.drgn_session._process = MagicMock()
        session.drgn_session._process.isalive.return_value = True
        yield session


class TestUnifiedSessionRouting:
    """Test command routing in UnifiedSession."""

    def test_routing_to_crash(self, unified_session):
        """Test crash commands are routed to crash engine."""
        unified_session.crash_session.execute_command = MagicMock(return_value="crash_output")
        unified_session.drgn_session.execute_command = MagicMock(return_value="drgn_output")
        
        # 'sys' -> crash
        assert unified_session.execute_command("sys") == "crash_output"
        unified_session.crash_session.execute_command.assert_called_with("sys", 60, True)
        
        # 'bt' -> crash
        assert unified_session.execute_command("bt") == "crash_output"
        
        # 'log' -> crash
        assert unified_session.execute_command("log") == "crash_output"

    def test_routing_to_drgn(self, unified_session):
        """Test drgn commands are routed to drgn engine."""
        unified_session.crash_session.execute_command = MagicMock(return_value="crash_output")
        unified_session.drgn_session.execute_command = MagicMock(return_value="drgn_output")
        
        # 'prog' -> drgn
        assert unified_session.execute_command("prog") == "drgn_output"
        unified_session.drgn_session.execute_command.assert_called_with("prog", 60, True)
        
        # Python assignment -> drgn
        assert unified_session.execute_command("x = 1") == "drgn_output"
        
        # Function call -> drgn
        assert unified_session.execute_command("find_task(1)") == "drgn_output"

    def test_explicit_routing(self, unified_session):
        """Test explicit routing with crash: and drgn: prefixes."""
        unified_session.crash_session.execute_command = MagicMock(return_value="crash_output")
        unified_session.drgn_session.execute_command = MagicMock(return_value="drgn_output")
        
        # Force crash for drgn-like command
        assert unified_session.execute_command("crash: prog") == "crash_output"
        unified_session.crash_session.execute_command.assert_called_with("prog", 60, True)
        
        # Force drgn for crash-like command
        assert unified_session.execute_command("drgn: sys") == "drgn_output"
        unified_session.drgn_session.execute_command.assert_called_with("sys", 60, True)
