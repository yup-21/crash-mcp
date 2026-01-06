#!/usr/bin/env python3
"""
Crash Utility Compiler

Compiles the crash utility from source with support for cross-architecture
debugging and various compression formats (LZO, Snappy, Zstd).

Usage:
    python -m crash_mcp.compile_crash --arch ARM64
    python -m crash_mcp.compile_crash --arch X86_64 --clean
"""
import os
import shutil
import subprocess
import logging
import argparse
import sys
import multiprocessing
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


# Supported architectures mapping
ARCH_MAPPING = {
    "arm64": ("ARM64", "-arm64"),
    "aarch64": ("ARM64", "-arm64"),
    "ppc64": ("PPC64", "-ppc64"),
    "ppc64le": ("PPC64LE", "-ppc64le"),
    "s390x": ("S390X", "-s390x"),
    "x86_64": (None, ""),  # Native, no target flag needed
    "amd64": (None, ""),
    "auto": (None, ""),
    "native": (None, ""),
}

# Compression library detection
COMPRESSION_LIBS = {
    "lzo": ["/usr/include/lzo/lzo1x.h", "/usr/include/lzo1x.h"],
    "snappy": ["/usr/include/snappy-c.h"],
    "zstd": ["/usr/include/zstd.h"],
}

# Required build dependencies
REQUIRED_DEPENDENCIES = {
    "binaries": ["git", "make", "gcc"],
    "apt_packages": [
        "git", "make", "gcc", "g++", "bison", "flex",
        "zlib1g-dev", "libgmp-dev", "libmpfr-dev", "libncurses-dev",
        "liblzma-dev", "texinfo",
        # Compression libs (optional but recommended)
        "liblzo2-dev", "libsnappy-dev", "libzstd-dev",
    ],
}


@dataclass
class BuildConfig:
    """Build configuration for crash utility."""
    arch: str = "auto"
    install_dir: Path = Path("./bin")
    source_dir: Path = Path("./build/crash_src")
    clean: bool = False
    jobs: int = 0  # 0 = auto-detect

    def __post_init__(self):
        self.install_dir = Path(self.install_dir).resolve()
        self.source_dir = Path(self.source_dir).resolve()
        if self.jobs == 0:
            self.jobs = multiprocessing.cpu_count()


def get_project_root() -> Path:
    """Get the project root directory."""
    # Find project root by looking for pyproject.toml
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "pyproject.toml").exists():
            return current
        current = current.parent
    # Fallback to current working directory
    return Path.cwd()


def check_dependencies() -> tuple[bool, list[str]]:
    """Check if required build dependencies are available."""
    missing = []
    for tool in REQUIRED_DEPENDENCIES["binaries"]:
        if not shutil.which(tool):
            missing.append(tool)
    return len(missing) == 0, missing


def detect_compression_libs() -> list[str]:
    """Detect available compression libraries."""
    available = []
    for lib_name, header_paths in COMPRESSION_LIBS.items():
        for path in header_paths:
            if os.path.exists(path):
                available.append(lib_name)
                break
    return available


def get_arch_config(arch: str) -> tuple[Optional[str], str]:
    """Get make target and binary suffix for architecture."""
    arch_lower = arch.lower()
    if arch_lower in ARCH_MAPPING:
        return ARCH_MAPPING[arch_lower]
    # Custom architecture
    return (arch.upper(), f"-{arch.lower()}")


def clone_or_update_source(source_dir: Path) -> bool:
    """Clone or update crash source code."""
    git_dir = source_dir / ".git"
    
    if git_dir.exists():
        logger.info("Updating existing crash source...")
        try:
            subprocess.run(
                ["git", "pull"],
                cwd=source_dir,
                check=True,
                capture_output=True,
            )
            return True
        except subprocess.CalledProcessError as e:
            logger.warning(f"Git pull failed: {e.stderr.decode() if e.stderr else e}")
            logger.info("Continuing with existing source...")
            return True
    else:
        logger.info("Cloning crash source from GitHub...")
        source_dir.parent.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                ["git", "clone", "https://github.com/crash-utility/crash.git", str(source_dir)],
                check=True,
            )
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to clone repository: {e}")
            return False


def build_crash(config: BuildConfig) -> Optional[Path]:
    """
    Build the crash utility.
    
    Returns:
        Path to the installed binary, or None if build failed.
    """
    # Check dependencies
    deps_ok, missing = check_dependencies()
    if not deps_ok:
        logger.error(f"Missing build dependencies: {', '.join(missing)}")
        logger.info("Install them with:")
        logger.info(f"  sudo apt-get install {' '.join(REQUIRED_DEPENDENCIES['apt_packages'])}")
        return None

    # Clone or update source
    if config.clean and config.source_dir.exists():
        logger.info(f"Cleaning source directory: {config.source_dir}")
        shutil.rmtree(config.source_dir)

    if not clone_or_update_source(config.source_dir):
        return None

    # Prepare make command
    make_cmd = ["make"]
    
    # Add architecture target
    target, binary_suffix = get_arch_config(config.arch)
    if target:
        make_cmd.append(f"target={target}")
    
    # Detect and add compression library support
    compression_libs = detect_compression_libs()
    for lib in compression_libs:
        make_cmd.append(lib)
        logger.info(f"Compression support enabled: {lib.upper()}")
    
    if not compression_libs:
        logger.warning("No compression libraries detected. Install liblzo2-dev, libsnappy-dev, or libzstd-dev for vmcore compression support.")

    # Add parallel jobs
    make_cmd.append(f"-j{config.jobs}")

    # Clean if requested (but source already exists)
    if config.clean:
        logger.info("Running make clean...")
        subprocess.run(["make", "clean"], cwd=config.source_dir, capture_output=True)

    # Build
    logger.info(f"Building crash utility...")
    logger.info(f"  Architecture: {config.arch}")
    logger.info(f"  Command: {' '.join(make_cmd)}")
    
    try:
        subprocess.run(make_cmd, cwd=config.source_dir, check=True)
    except subprocess.CalledProcessError:
        logger.error("Compilation failed!")
        return None

    # Install binary
    src_binary = config.source_dir / "crash"
    if not src_binary.exists():
        logger.error("Build completed but 'crash' binary not found.")
        return None

    config.install_dir.mkdir(parents=True, exist_ok=True)
    dest_name = f"crash{binary_suffix}"
    dest_path = config.install_dir / dest_name

    shutil.copy2(src_binary, dest_path)
    dest_path.chmod(0o755)

    logger.info(f"Successfully installed: {dest_path}")
    return dest_path


def print_install_instructions():
    """Print dependency installation instructions."""
    print("\n" + "=" * 60)
    print("DEPENDENCY INSTALLATION")
    print("=" * 60)
    print("\nFor Ubuntu/Debian:")
    print(f"  sudo apt-get install {' '.join(REQUIRED_DEPENDENCIES['apt_packages'])}")
    print("\nFor CentOS/RHEL/Fedora:")
    print("  sudo dnf install git make gcc gcc-c++ bison flex \\")
    print("    zlib-devel gmp-devel mpfr-devel ncurses-devel xz-devel \\")
    print("    texinfo lzo-devel snappy-devel libzstd-devel")
    print("=" * 60 + "\n")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Compile and install crash utility for vmcore analysis.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                      # Build for native architecture
  %(prog)s --arch ARM64         # Build for ARM64 vmcore analysis
  %(prog)s --arch ARM64 --clean # Clean build for ARM64
  %(prog)s --deps               # Show dependency installation instructions

Supported Architectures:
  auto/native/x86_64  - Native x86_64 (default)
  arm64/aarch64       - ARM64 / AArch64
  ppc64/ppc64le       - PowerPC 64-bit
  s390x               - IBM Z (s390x)
        """,
    )
    parser.add_argument(
        "--arch", "-a",
        default="auto",
        help="Target architecture for vmcore analysis (default: auto)",
    )
    parser.add_argument(
        "--install-dir", "-i",
        default=None,
        help="Installation directory (default: ./bin or project/bin)",
    )
    parser.add_argument(
        "--source-dir", "-s",
        default=None,
        help="Source code directory (default: ./build/crash_src)",
    )
    parser.add_argument(
        "--clean", "-c",
        action="store_true",
        help="Clean build (remove existing source and rebuild)",
    )
    parser.add_argument(
        "--jobs", "-j",
        type=int,
        default=0,
        help="Number of parallel jobs (default: auto)",
    )
    parser.add_argument(
        "--deps",
        action="store_true",
        help="Show dependency installation instructions and exit",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output",
    )

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    if args.deps:
        print_install_instructions()
        return 0

    # Determine directories
    project_root = get_project_root()
    install_dir = Path(args.install_dir) if args.install_dir else project_root / "bin"
    source_dir = Path(args.source_dir) if args.source_dir else project_root / "build" / "crash_src"

    config = BuildConfig(
        arch=args.arch,
        install_dir=install_dir,
        source_dir=source_dir,
        clean=args.clean,
        jobs=args.jobs,
    )

    logger.info(f"Target Architecture: {config.arch}")
    logger.info(f"Install Directory: {config.install_dir}")
    logger.info(f"Source Directory: {config.source_dir}")

    result = build_crash(config)
    if result:
        print(f"\n✅ Crash utility installed to: {result}")
        print("You can now use it to analyze vmcore files.")
        return 0
    else:
        print("\n❌ Build failed. Check the logs above for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
