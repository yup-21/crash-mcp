"""Test CrashDiscovery functionality."""
import pytest
import os
from crash_mcp.discovery import CrashDiscovery


class TestCrashDiscovery:
    """Test suite for CrashDiscovery."""

    def test_find_dumps(self, tmp_path):
        """Test finding vmcore dump files."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        vmcore = subdir / "vmcore"
        vmcore.write_text("dummy dump content")
        
        dumps = CrashDiscovery.find_dumps([str(tmp_path)])
        assert len(dumps) == 1
        assert dumps[0]['filename'] == "vmcore"
        assert dumps[0]['path'] == str(vmcore)

    def test_find_dumps_multiple(self, tmp_path):
        """Test finding multiple dump files."""
        for i in range(3):
            subdir = tmp_path / f"crash_{i}"
            subdir.mkdir()
            (subdir / "vmcore").write_text(f"dump {i}")
        
        dumps = CrashDiscovery.find_dumps([str(tmp_path)])
        assert len(dumps) == 3

    def test_match_kernel(self, tmp_path):
        """Test matching vmlinux to vmcore."""
        dump_dir = tmp_path / "dump_loc"
        dump_dir.mkdir()
        
        vmcore = dump_dir / "vmcore"
        vmcore.write_text("content")
        
        vmlinux = dump_dir / "vmlinux-6.5.0"
        vmlinux.write_text("kernel")
        
        match = CrashDiscovery.match_kernel(str(vmcore), [str(tmp_path)])
        assert match == str(vmlinux)

    def test_match_kernel_not_found(self, tmp_path):
        """Test kernel not found case."""
        dump_dir = tmp_path / "dump_loc"
        dump_dir.mkdir()
        vmcore = dump_dir / "vmcore"
        vmcore.write_text("content")
        
        match = CrashDiscovery.match_kernel(str(vmcore), [str(tmp_path)])
        assert match is None

    def test_ignore_log_files(self, tmp_path):
        """Test that log files are ignored."""
        subdir = tmp_path / "crash"
        subdir.mkdir()
        (subdir / "vmcore").write_text("dump")
        (subdir / "vmcore.log").write_text("log")
        (subdir / "vmcore.txt").write_text("text")
        
        dumps = CrashDiscovery.find_dumps([str(tmp_path)])
        assert len(dumps) == 1
        assert dumps[0]['filename'] == "vmcore"
