"""Test CommandStore functionality."""
import pytest
from crash_mcp.common.command_store import CommandStore, CommandResult


class TestCommandStore:
    """Test suite for CommandStore."""

    def test_save_command(self, temp_workdir):
        """Test saving command output."""
        store = CommandStore(temp_workdir)
        result = store.save("crash", "sys", "system info output", {})
        
        assert result.command == "sys"
        assert result.engine == "crash"
        assert result.total_lines == 1
        assert not result.cached
        assert result.output_file.exists()

    def test_get_cached(self, temp_workdir):
        """Test cache retrieval."""
        store = CommandStore(temp_workdir)
        store.save("crash", "bt", "backtrace output", {})
        
        cached = store.get_cached("crash", "bt", {})
        assert cached is not None
        assert cached.cached is True
        assert cached.command == "bt"

    def test_cache_miss(self, temp_workdir):
        """Test cache miss."""
        store = CommandStore(temp_workdir)
        cached = store.get_cached("crash", "nonexistent", {})
        assert cached is None

    def test_get_lines(self, temp_workdir):
        """Test line pagination."""
        store = CommandStore(temp_workdir)
        multiline = "\n".join([f"line {i}" for i in range(100)])
        store.save("crash", "log", multiline, {})
        
        text, count, total, has_more = store.get_lines("crash:log", 0, 10)
        assert count == 10
        assert total == 100
        assert has_more is True
        assert "line 0" in text

    def test_get_lines_offset(self, temp_workdir):
        """Test line pagination with offset."""
        store = CommandStore(temp_workdir)
        multiline = "\n".join([f"line {i}" for i in range(100)])
        store.save("crash", "log", multiline, {})
        
        text, count, total, has_more = store.get_lines("crash:log", 90, 20)
        assert count == 10  # Only 10 lines left
        assert has_more is False
        assert "line 99" in text

    def test_search(self, temp_workdir):
        """Test regex search."""
        store = CommandStore(temp_workdir)
        content = """line 1: normal
line 2: ERROR: something failed
line 3: normal
line 4: ERROR: another failure
line 5: normal"""
        store.save("crash", "log", content, {})
        
        matches = store.search("crash:log", "ERROR")
        assert len(matches) == 2
        assert matches[0]["line_number"] == 2
        assert "ERROR" in matches[0]["line"]

    def test_search_with_context(self, temp_workdir):
        """Test search with context lines."""
        store = CommandStore(temp_workdir)
        content = "\n".join([f"line {i}" for i in range(10)])
        store.save("crash", "test", content, {})
        
        matches = store.search("crash:test", "line 5", context_lines=2)
        assert len(matches) == 1
        assert len(matches[0]["context_before"]) == 2
        assert len(matches[0]["context_after"]) == 2

    def test_context_dependent_id(self, temp_workdir):
        """Test command ID includes context."""
        store = CommandStore(temp_workdir)
        result1 = store.save("crash", "bt", "output1", {"pid": "1234"})
        result2 = store.save("crash", "bt", "output2", {"pid": "5678"})
        
        # Different context = different command_id
        assert result1.command_id != result2.command_id
        assert "@pid=" in result1.command_id
