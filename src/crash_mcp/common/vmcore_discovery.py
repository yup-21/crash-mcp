import os
import glob
from typing import List, Optional, Dict
import logging

logger = logging.getLogger(__name__)

# Common crash dump names
DUMP_PATTERNS = ["vmcore*", "core.*", "*.dump", "crash.*"]
# Common kernel image names
KERNEL_PATTERNS = ["vmlinux*", "System.map*"]

# Files to ignore even if they match DUMP_PATTERNS
IGNORE_EXTENSIONS = [".txt", ".log", ".gz", ".tar"]
IGNORE_PATTERNS = ["dmesg", "readme", "log"]

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
                        # Filter out unwanted files
                        filename = os.path.basename(filepath)
                        if any(filename.endswith(ext) for ext in IGNORE_EXTENSIONS):
                            continue
                        if any(pat in filename for pat in IGNORE_PATTERNS):
                            continue

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
        Extract kernel version from vmcore kdump header.
        
        Returns:
            Kernel version string (e.g., "5.15.0-generic") or None
        """
        from crash_mcp.common.arch_detect import get_vmcore_kernel_version
        return get_vmcore_kernel_version(dump_path)

    @staticmethod
    def get_arch_from_dump(dump_path: str) -> Optional[Dict[str, str]]:
        """
        Detect architecture from vmcore ELF header.
        
        Returns:
            Dict with 'machine', 'bits', 'endian' or None if detection fails
        """
        from crash_mcp.common.arch_detect import detect_elf_arch
        
        arch_info = detect_elf_arch(dump_path)
        if arch_info:
            return {
                "machine": arch_info.machine,
                "bits": arch_info.bits,
                "endian": arch_info.endian,
                "binary_suffix": arch_info.binary_suffix
            }
        return None

    @staticmethod
    def get_dump_info(dump_path: str) -> Optional[Dict]:
        """
        Get comprehensive information from vmcore file.
        
        Returns:
            Dict with 'kernel_version', 'hostname', 'arch', 'build_info' etc.
        """
        from crash_mcp.common.arch_detect import parse_kdump_header
        
        info = parse_kdump_header(dump_path)
        if info:
            return {
                "kernel_version": info.release,
                "hostname": info.node,
                "arch": info.machine,
                "normalized_arch": info.normalized_arch,
                "build_info": info.version_string,
                "domain": info.domain,
                "system": info.system,
                "kdump_version": info.version
            }
        return None

    @staticmethod
    def check_version_match(vmcore_path: str, vmlinux_path: str) -> Dict:
        """
        Check if vmcore and vmlinux kernel versions match.
        
        Returns:
            Dict with 'match', 'vmcore_version', 'vmlinux_version', 'message'
        """
        from crash_mcp.common.arch_detect import check_vmcore_vmlinux_match
        return check_vmcore_vmlinux_match(vmcore_path, vmlinux_path)
