"""Test DrgnSession functionality."""
import pytest
from crash_mcp.drgn.session import DrgnSession


@pytest.fixture
def drgn_session(mock_drgn_path):
    """Create a DrgnSession with mock drgn binary."""
    session = DrgnSession(
        dump_path='/tmp/vmcore',
        kernel_path='/tmp/vmlinux',
        binary_path=mock_drgn_path
    )
    yield session
    session.close()


class TestDrgnSession:
    """Test suite for DrgnSession."""

    def test_start_session(self, drgn_session):
        """Test session starts correctly."""
        drgn_session.start()
        assert drgn_session.is_active()

    def test_execute_command(self, drgn_session):
        """Test executing 'prog' command."""
        drgn_session.start()
        output = drgn_session.execute_command('prog')
        assert "CoreDump(prog, '/path/to/vmcore')" in output

    def test_execute_command_assignment(self, drgn_session):
        """Test executing Python assignment (no output expected)."""
        drgn_session.start()
        output = drgn_session.execute_command('task = find_task(prog, 1)')
        assert output == ""

    def test_execute_command_attribute(self, drgn_session):
        """Test executing attribute access."""
        drgn_session.start()
        drgn_session.execute_command('task = find_task(prog, 1)')
        output = drgn_session.execute_command('task.comm')
        assert '"systemd"' in output

    def test_close_session(self, drgn_session):
        """Test session closes correctly."""
        drgn_session.start()
        drgn_session.close()
        assert not drgn_session.is_active()
