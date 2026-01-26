"""Integration tests for crash-mcp workflow."""
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path


class TestFullWorkflow:
    """Test end-to-end workflow scenarios."""

    def test_discovery_to_session_flow(self, tmp_path):
        """Test discovering dumps and matching kernels."""
        from crash_mcp.discovery import CrashDiscovery
        
        # Create mock crash dump structure
        crash_dir = tmp_path / "var" / "crash" / "127.0.0.1-2024-01-01"
        crash_dir.mkdir(parents=True)
        vmcore = crash_dir / "vmcore"
        vmcore.write_text("crash dump content")
        vmlinux = crash_dir / "vmlinux"
        vmlinux.write_text("kernel image")
        
        # Discover dumps
        dumps = CrashDiscovery.find_dumps([str(tmp_path)])
        assert len(dumps) == 1
        
        # Match kernel
        kernel = CrashDiscovery.match_kernel(dumps[0]['path'], [str(tmp_path)])
        assert kernel == str(vmlinux)

    def test_command_store_workflow(self, temp_workdir):
        """Test command execution and retrieval workflow."""
        from crash_mcp.common.command_store import CommandStore
        
        store = CommandStore(temp_workdir)
        
        # Execute and save
        output = "PID: 1\nCOMM: init\nSTATUS: running"
        result = store.save("crash", "ps", output, {})
        
        # Retrieve first page
        text, count, total, has_more = store.get_lines(result.command_id, 0, 2)
        assert count == 2
        assert has_more is True
        
        # Search for pattern
        matches = store.search(result.command_id, "init")
        assert len(matches) == 1
        assert matches[0]["line_number"] == 2

    @patch('crash_mcp.crash.session.pexpect.spawn')
    @patch('crash_mcp.drgn.session.pexpect.spawn')
    def test_unified_session_engine_selection(self, mock_drgn_spawn, mock_crash_spawn, temp_workdir):
        """Test unified session correctly selects engine based on command."""
        from crash_mcp.common.unified_session import UnifiedSession
        
        session = UnifiedSession('/tmp/vmcore', '/tmp/vmlinux', workdir=temp_workdir)
        
        # Mock process
        session.crash_session._process = MagicMock()
        session.crash_session._process.isalive.return_value = True
        session.drgn_session._process = MagicMock()
        session.drgn_session._process.isalive.return_value = True
        
        # Mock execute methods
        session.crash_session.execute_command = MagicMock(return_value="crash output")
        session.drgn_session.execute_command = MagicMock(return_value="drgn output")
        
        # Test command routing
        crash_cmds = ["sys", "bt", "ps", "log"]
        drgn_cmds = ["prog", "find_task(prog, 1)", "x = 1"]
        
        for cmd in crash_cmds:
            session.execute_command(cmd)
            session.crash_session.execute_command.assert_called()
        
        for cmd in drgn_cmds:
            session.execute_command(cmd)
            session.drgn_session.execute_command.assert_called()
