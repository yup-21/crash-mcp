"""
Architecture detection and crash binary selection utilities.

Detects vmcore architecture from ELF header and selects appropriate crash binary.
"""
import os
import struct
import logging
from pathlib import Path
from typing import Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ELF Machine type to architecture mapping
# Reference: /usr/include/elf.h
ELF_MACHINE_TYPES = {
    3: ("i386", "x86"),
    62: ("x86_64", "x86_64"),
    183: ("aarch64", "arm64"),
    20: ("ppc", "ppc"),
    21: ("ppc64", "ppc64"),
    22: ("s390", "s390x"),
    243: ("riscv", "riscv64"),
    258: ("loongarch", "loongarch64"),
}

# Crash binary suffix mapping
ARCH_TO_BINARY_SUFFIX = {
    "x86_64": "",  # Native, no suffix
    "i386": "",    # Native on 32-bit or x86_64
    "arm64": "-arm64",
    "aarch64": "-arm64",
    "ppc64": "-ppc64",
    "ppc64le": "-ppc64le",
    "s390x": "-s390x",
    "riscv64": "-riscv64",
    "loongarch64": "-loongarch64",
}


@dataclass
class ArchInfo:
    """Architecture information from ELF header."""
    machine: str        # Architecture name (e.g., "x86_64", "aarch64")
    bits: int           # 32 or 64
    endian: str         # "little" or "big"
    elf_machine: int    # Raw ELF e_machine value
    
    @property
    def binary_suffix(self) -> str:
        """Get the crash binary suffix for this architecture."""
        return ARCH_TO_BINARY_SUFFIX.get(self.machine, f"-{self.machine}")


@dataclass
class KdumpInfo:
    """Information extracted from kdump header."""
    signature: str          # "KDUMP" or "KDUMP   " with version
    version: int            # Kdump format version
    system: str             # OS name (usually "Linux")
    node: str               # Hostname
    release: str            # Kernel release (e.g., "5.15.0-generic")
    version_string: str     # Build version string (e.g., "#1 SMP ...")
    machine: str            # Architecture (e.g., "x86_64", "aarch64")
    domain: str             # Domain name
    
    @property
    def kernel_version(self) -> str:
        """Get the full kernel version string."""
        return self.release
    
    @property
    def normalized_arch(self) -> str:
        """Get normalized architecture name for crash binary selection."""
        arch = self.machine.lower()
        if arch in ("aarch64",):
            return "arm64"
        elif arch in ("x86_64", "amd64"):
            return "x86_64"
        return arch


def parse_kdump_header(filepath: str) -> Optional[KdumpInfo]:
    """
    Parse kdump header from vmcore file.
    
    The kdump header format (makedumpfile):
    - 0x00-0x07: Signature "KDUMP   " (8 bytes)
    - 0x08-0x0B: Version (4 bytes, little-endian)
    - 0x0C+: utsname structure (6 fields × 65 bytes each = 390 bytes)
      - sysname (65 bytes)
      - nodename (65 bytes)  
      - release (65 bytes) - kernel version
      - version (65 bytes) - build info
      - machine (65 bytes) - architecture
      - domainname (65 bytes)
    
    Args:
        filepath: Path to vmcore file
        
    Returns:
        KdumpInfo object or None if not a kdump file
    """
    # utsname field size (defined in linux/utsname.h as __NEW_UTS_LEN + 1 = 65)
    UTS_FIELD_SIZE = 65
    
    try:
        with open(filepath, 'rb') as f:
            # Read signature (8 bytes)
            sig = f.read(8)
            if not sig.startswith(b'KDUMP'):
                logger.debug(f"{filepath} is not a kdump file (signature: {sig[:8]})")
                return None
            
            # Read version (4 bytes, little-endian)
            version = struct.unpack('<I', f.read(4))[0]
            
            # Helper to read null-terminated string from fixed-size field
            def read_field(size: int = UTS_FIELD_SIZE) -> str:
                data = f.read(size)
                # Find null terminator
                null_pos = data.find(b'\x00')
                if null_pos >= 0:
                    data = data[:null_pos]
                return data.decode('utf-8', errors='replace').strip()
            
            # Read utsname fields (each 65 bytes)
            system = read_field()
            node = read_field()
            release = read_field()
            version_string = read_field()
            machine = read_field()
            domain = read_field()
            
            info = KdumpInfo(
                signature=sig.decode('ascii', errors='replace').strip(),
                version=version,
                system=system,
                node=node,
                release=release,
                version_string=version_string,
                machine=machine,
                domain=domain
            )
            
            logger.info(f"Parsed kdump header: {info.release} on {info.machine}")
            return info
            
    except (IOError, struct.error) as e:
        logger.error(f"Failed to parse kdump header from {filepath}: {e}")
        return None


def get_vmcore_kernel_version(vmcore_path: str) -> Optional[str]:
    """
    Extract kernel version from vmcore file.
    
    Args:
        vmcore_path: Path to vmcore file
        
    Returns:
        Kernel version string (e.g., "5.15.0-generic") or None
    """
    info = parse_kdump_header(vmcore_path)
    if info:
        return info.release
    return None


def match_vmlinux_version(vmlinux_path: str) -> Optional[str]:
    """
    Extract kernel version from vmlinux file.
    
    This attempts to find the kernel version string embedded in vmlinux.
    Common patterns: "Linux version X.Y.Z-..."
    
    Args:
        vmlinux_path: Path to vmlinux file
        
    Returns:
        Kernel version string or None
    """
    import subprocess
    import re
    
    try:
        # Use strings command to find version string
        result = subprocess.run(
            ['strings', vmlinux_path],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        # Look for "Linux version X.Y.Z" pattern
        for line in result.stdout.split('\n'):
            if line.startswith('Linux version '):
                # Extract version: "Linux version 5.15.0-generic ..."
                match = re.match(r'Linux version (\S+)', line)
                if match:
                    return match.group(1)
            # Also try just version pattern
            elif re.match(r'^\d+\.\d+\.\d+[-\w.]*$', line):
                return line
                
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError) as e:
        logger.debug(f"Failed to extract version from vmlinux: {e}")
    
    return None


def check_vmcore_vmlinux_match(vmcore_path: str, vmlinux_path: str) -> dict:
    """
    Check if vmcore and vmlinux versions match.
    
    Args:
        vmcore_path: Path to vmcore file
        vmlinux_path: Path to vmlinux file
        
    Returns:
        Dict with 'match' (bool), 'vmcore_version', 'vmlinux_version', 'message'
    """
    vmcore_version = get_vmcore_kernel_version(vmcore_path)
    vmlinux_version = match_vmlinux_version(vmlinux_path)
    
    result = {
        'vmcore_version': vmcore_version,
        'vmlinux_version': vmlinux_version,
        'match': False,
        'message': ''
    }
    
    if not vmcore_version:
        result['message'] = "Could not detect vmcore kernel version"
        return result
    
    if not vmlinux_version:
        result['message'] = "Could not detect vmlinux kernel version"
        return result
    
    # Compare versions
    if vmcore_version == vmlinux_version:
        result['match'] = True
        result['message'] = f"Versions match: {vmcore_version}"
    else:
        # Check if they're close (same base version)
        vmcore_base = vmcore_version.split('-')[0]
        vmlinux_base = vmlinux_version.split('-')[0]
        
        if vmcore_base == vmlinux_base:
            result['message'] = (
                f"Warning: Version mismatch but same base version.\n"
                f"  vmcore: {vmcore_version}\n"
                f"  vmlinux: {vmlinux_version}"
            )
        else:
            result['message'] = (
                f"ERROR: Version mismatch!\n"
                f"  vmcore: {vmcore_version}\n"
                f"  vmlinux: {vmlinux_version}\n"
                f"Analysis may fail or produce incorrect results."
            )
    
    return result




def detect_elf_arch(filepath: str) -> Optional[ArchInfo]:
    """
    Detect architecture from ELF file header.
    Works with vmcore (kdump), vmlinux, or any ELF file.
    
    Args:
        filepath: Path to ELF file
        
    Returns:
        ArchInfo object or None if detection fails
    """
    try:
        with open(filepath, 'rb') as f:
            # Read ELF magic
            magic = f.read(4)
            if magic != b'\x7fELF':
                logger.debug(f"{filepath} is not an ELF file")
                return None
            
            # EI_CLASS: 32-bit (1) or 64-bit (2)
            ei_class = struct.unpack('B', f.read(1))[0]
            bits = 32 if ei_class == 1 else 64
            
            # EI_DATA: Little endian (1) or big endian (2)
            ei_data = struct.unpack('B', f.read(1))[0]
            endian = "little" if ei_data == 1 else "big"
            byte_order = '<' if ei_data == 1 else '>'
            
            # Skip to e_machine (offset 18 in ELF header)
            f.seek(18)
            e_machine = struct.unpack(f'{byte_order}H', f.read(2))[0]
            
            # Map machine type to architecture name
            if e_machine in ELF_MACHINE_TYPES:
                arch_name, normalized = ELF_MACHINE_TYPES[e_machine]
            else:
                arch_name = f"unknown-{e_machine}"
                normalized = arch_name
            
            return ArchInfo(
                machine=normalized,
                bits=bits,
                endian=endian,
                elf_machine=e_machine
            )
            
    except (IOError, struct.error) as e:
        logger.error(f"Failed to read ELF header from {filepath}: {e}")
        return None


def detect_vmcore_arch(vmcore_path: str, vmlinux_path: str = None) -> Optional[ArchInfo]:
    """
    Detect architecture from vmcore or vmlinux.
    
    For kdump vmcore files, the architecture is determined from the ELF header.
    As a fallback, vmlinux can be used if vmcore detection fails.
    
    Args:
        vmcore_path: Path to vmcore file
        vmlinux_path: Optional path to vmlinux file as fallback
        
    Returns:
        ArchInfo or None
    """
    # Try vmcore first
    if os.path.exists(vmcore_path):
        arch = detect_elf_arch(vmcore_path)
        if arch:
            logger.info(f"Detected vmcore architecture: {arch.machine} ({arch.bits}-bit, {arch.endian} endian)")
            return arch
    
    # Fallback to vmlinux
    if vmlinux_path and os.path.exists(vmlinux_path):
        arch = detect_elf_arch(vmlinux_path)
        if arch:
            logger.info(f"Detected vmlinux architecture: {arch.machine} ({arch.bits}-bit, {arch.endian} endian)")
            return arch
    
    logger.warning(f"Could not detect architecture from {vmcore_path}")
    return None


def get_host_arch() -> str:
    """Get the host machine architecture."""
    import platform
    machine = platform.machine().lower()
    # Normalize
    if machine in ("x86_64", "amd64"):
        return "x86_64"
    elif machine in ("aarch64", "arm64"):
        return "arm64"
    elif machine in ("ppc64le",):
        return "ppc64le"
    return machine


def find_crash_binary(
    target_arch: str = None,
    vmcore_path: str = None,
    vmlinux_path: str = None,
    search_dirs: list = None,
    binary_name: str = "crash"
) -> Tuple[str, str]:
    """
    Find the appropriate crash binary for the target architecture.
    
    Args:
        target_arch: Target architecture (e.g., "arm64"). If None, auto-detect from vmcore.
        vmcore_path: Path to vmcore for auto-detection
        vmlinux_path: Path to vmlinux for auto-detection fallback
        search_dirs: Directories to search for crash binaries
        binary_name: Base name of crash binary (default: "crash")
        
    Returns:
        Tuple of (binary_path, detected_arch)
        
    Raises:
        FileNotFoundError: If no suitable crash binary is found
    """
    # Auto-detect architecture if not specified
    detected_arch = None
    if target_arch:
        detected_arch = target_arch.lower()
    elif vmcore_path:
        arch_info = detect_vmcore_arch(vmcore_path, vmlinux_path)
        if arch_info:
            detected_arch = arch_info.machine
    
    if not detected_arch:
        # Default to host architecture
        detected_arch = get_host_arch()
        logger.info(f"Using host architecture: {detected_arch}")
    
    # Determine binary suffix
    suffix = ARCH_TO_BINARY_SUFFIX.get(detected_arch, f"-{detected_arch}")
    target_binary = f"{binary_name}{suffix}"
    
    # Default search directories
    if search_dirs is None:
        search_dirs = []
        
        # 1. Project bin directory
        project_root = Path(__file__).resolve().parent.parent.parent
        search_dirs.append(project_root / "bin")
        
        # 2. Current working directory bin
        search_dirs.append(Path.cwd() / "bin")
        
        # 3. System paths
        search_dirs.extend([
            Path("/usr/bin"),
            Path("/usr/local/bin"),
            Path("/usr/sbin"),
            Path.home() / ".local" / "bin",
        ])
    
    # Search for the binary
    for search_dir in search_dirs:
        search_dir = Path(search_dir)
        if not search_dir.exists():
            continue
            
        # Try architecture-specific binary first
        binary_path = search_dir / target_binary
        if binary_path.exists() and os.access(binary_path, os.X_OK):
            logger.info(f"Found crash binary: {binary_path} for {detected_arch}")
            return str(binary_path), detected_arch
        
        # Try generic "crash" binary (might work for native arch)
        if suffix and detected_arch == get_host_arch():
            generic_path = search_dir / binary_name
            if generic_path.exists() and os.access(generic_path, os.X_OK):
                logger.info(f"Found generic crash binary: {generic_path} for native {detected_arch}")
                return str(generic_path), detected_arch
    
    # Check if crash is in PATH
    import shutil
    path_binary = shutil.which(target_binary)
    if path_binary:
        logger.info(f"Found crash binary in PATH: {path_binary}")
        return path_binary, detected_arch
    
    # Fallback: generic crash in PATH
    if suffix:
        path_binary = shutil.which(binary_name)
        if path_binary and detected_arch == get_host_arch():
            logger.info(f"Found generic crash binary in PATH: {path_binary}")
            return path_binary, detected_arch
    
    # Not found
    searched = [str(d) for d in search_dirs if Path(d).exists()]
    raise FileNotFoundError(
        f"Crash binary '{target_binary}' not found for architecture '{detected_arch}'.\n"
        f"Searched directories: {searched}\n"
        f"Please compile the crash tool with: compile-crash --arch {detected_arch.upper()}"
    )


def list_available_crash_binaries(search_dirs: list = None) -> list:
    """
    List all available crash binaries and their architectures.
    
    Returns:
        List of dicts with 'path', 'arch', 'is_native'
    """
    if search_dirs is None:
        search_dirs = []
        project_root = Path(__file__).resolve().parent.parent.parent
        search_dirs.append(project_root / "bin")
        search_dirs.append(Path.cwd() / "bin")
    
    host_arch = get_host_arch()
    binaries = []
    
    for search_dir in search_dirs:
        search_dir = Path(search_dir)
        if not search_dir.exists():
            continue
            
        for item in search_dir.iterdir():
            if item.is_file() and item.name.startswith("crash") and os.access(item, os.X_OK):
                name = item.name
                if name == "crash":
                    arch = host_arch
                elif name.startswith("crash-"):
                    arch = name[6:]  # Remove "crash-" prefix
                else:
                    continue
                    
                binaries.append({
                    "path": str(item),
                    "arch": arch,
                    "is_native": arch == host_arch
                })
    
    return binaries
