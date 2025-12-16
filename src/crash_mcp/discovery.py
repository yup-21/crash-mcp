import os
import glob
from typing import List, Optional, Dict
import logging

logger = logging.getLogger(__name__)

# Common crash dump names
DUMP_PATTERNS = ["vmcore", "core.*", "*.dump", "crash.*"]
# Common kernel image names
KERNEL_PATTERNS = ["vmlinux*", "System.map*"]

class CrashDiscovery:
    """
    Helper to discover crash dumps and matching kernels.
    """

    @staticmethod
    def find_dumps(search_paths: List[str]) -> List[Dict[str, str]]:
        """
        Scans given paths for crash dump files.
        Returns a list of dicts with 'path', 'filename', 'size', 'modified'.
        """
        dumps = []
        for path in search_paths:
            if not os.path.isdir(path):
                continue
            
            for pattern in DUMP_PATTERNS:
                full_pattern = os.path.join(path, "**", pattern)
                # recursive search
                for filepath in glob.glob(full_pattern, recursive=True):
                    if os.path.isfile(filepath):
                        stat = os.stat(filepath)
                        dumps.append({
                            "path": filepath,
                            "filename": os.path.basename(filepath),
                            "size": stat.st_size,
                            "modified": stat.st_mtime
                        })
        return dumps

    @staticmethod
    def match_kernel(dump_path: str, search_paths: List[str]) -> Optional[str]:
        """
        Attempts to find a matching kernel/debuginfo for the specific dump.
        This is a heuristic implementation.
        """
        # 1. Look in the same directory as the dump
        dump_dir = os.path.dirname(dump_path)
        for pattern in KERNEL_PATTERNS:
            matches = glob.glob(os.path.join(dump_dir, pattern))
            if matches:
                 # Prefer vmlinux over system.map if multiple, or just take first
                 # simple heuristic: look for vmlinux explicitly first
                 vmlinux = next((m for m in matches if "vmlinux" in os.path.basename(m)), None)
                 if vmlinux:
                     return vmlinux
                 return matches[0]

        # 2. Look in global search paths (e.g. /usr/lib/debug/lib/modules...)
        # This is where we would implement more complex logic based on `file` output of the dump
        # to get the kernel version string.
        # For now, we return None if not found alongside.
        
        return None
        
    @staticmethod
    def get_kernel_version_from_dump(dump_path: str) -> Optional[str]:
        """
        Placeholder: read dump header to extract kernel version.
        Useful for precise matching.
        """
        # Would require invoking 'crash --minimal' or 'file' command
        return None
