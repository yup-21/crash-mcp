"""Test CrashSession functionality."""
import pytest
from crash_mcp.crash.session import CrashSession


@pytest.fixture
def crash_session(mock_crash_path):
    """Create a CrashSession with mock crash binary."""
    session = CrashSession(
        dump_path="vmcore_dummy",
        kernel_path="vmlinux_dummy",
        binary_path=mock_crash_path
    )
    yield session
    session.close()


class TestCrashSession:
    """Test suite for CrashSession."""

    def test_session_start(self, crash_session):
        """Test session starts correctly."""
        crash_session.start(timeout=5)
        assert crash_session.is_active()

    def test_execute_sys_command(self, crash_session):
        """Test executing 'sys' command."""
        crash_session.start(timeout=5)
        output = crash_session.execute_command("sys")
        assert "KERNEL:" in output
        assert "DUMPFILE:" in output

    def test_execute_bt_command(self, crash_session):
        """Test executing 'bt' command."""
        crash_session.start(timeout=5)
        output = crash_session.execute_command("bt")
        assert "mock output for: bt" in output

    def test_session_close(self, crash_session):
        """Test session closes correctly."""
        crash_session.start(timeout=5)
        assert crash_session.is_active()
        crash_session.close()
        assert not crash_session.is_active()
