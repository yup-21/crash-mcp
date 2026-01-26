#!/usr/bin/env python3
"""
Crash Utility Compiler

Compiles the crash utility from source with support for cross-architecture
debugging and various compression formats (LZO, Snappy, Zstd).
Compiles the crash utility from source with support for cross-architecture
debugging and various compression formats (LZO, Snappy, Zstd).
Installs pykdump and other common extensions by default.

Usage:
    python -m crash_mcp.compile_crash --arch ARM64
    python -m crash_mcp.compile_crash --without-pykdump
    python -m crash_mcp.compile_crash --without-extensions
"""
import os
import shutil
import subprocess
import logging
import argparse
import sys
import multiprocessing
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from crash_mcp.builder import utils as build_utils

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

# Pykdump pre-built binaries are only available for crash 7/8
# When using pykdump binary download, default to this version
PYKDUMP_COMPATIBLE_CRASH_VERSION = "8.0.5"


@dataclass
class BuildConfig:
    """Build configuration for crash utility."""
    arch: str = "auto"
    version: str = "latest"  # "latest" or specific version like "9.0.1"
    install_dir: Path = field(default_factory=lambda: Path("./bin"))
    source_dir: Path = field(default_factory=lambda: Path("./build/crash_src"))
    clean: bool = False
    jobs: int = 0  # 0 = auto-detect

    def __post_init__(self):
        self.install_dir = Path(self.install_dir).resolve()
        self.source_dir = Path(self.source_dir).resolve()
        if self.jobs == 0:
            self.jobs = multiprocessing.cpu_count()


def get_arch_config(arch: str) -> tuple[Optional[str], str]:
    """Get make target and binary suffix for architecture."""
    arch_lower = arch.lower()
    if arch_lower in ARCH_MAPPING:
        return ARCH_MAPPING[arch_lower]
    return (arch.upper(), f"-{arch.lower()}")


def build_crash(config: BuildConfig) -> Optional[Path]:
    """Build the crash utility."""
    # Check dependencies
    deps_ok, missing = build_utils.check_dependencies(REQUIRED_DEPENDENCIES["binaries"])
    if not deps_ok:
        logger.error(f"Missing: {', '.join(missing)}. Run: sudo apt-get install {' '.join(REQUIRED_DEPENDENCIES['apt_packages'])}")
        return None

    # Clone/update source
    if config.clean and config.source_dir.exists():
        shutil.rmtree(config.source_dir)
    
    if not build_utils.clone_or_update_repo("https://github.com/crash-utility/crash.git", config.source_dir):
        return None
    if not build_utils.checkout_version(config.source_dir, config.version):
        return None

    # Build command
    target, binary_suffix = get_arch_config(config.arch)
    make_cmd = ["make"] + ([f"target={target}"] if target else [])
    
    # Detect compression libs
    for lib, paths in COMPRESSION_LIBS.items():
        if any(os.path.exists(p) for p in paths):
            make_cmd.append(lib)
    
    make_cmd.append(f"-j{config.jobs}")
    if config.clean:
        subprocess.run(["make", "clean"], cwd=config.source_dir, capture_output=True)
    
    logger.info(f"Building: {' '.join(make_cmd)}")
    
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
    print("\nUbuntu/Debian:")
    print(f"  sudo apt-get install {' '.join(REQUIRED_DEPENDENCIES['apt_packages'])}")
    print("\nCentOS/RHEL/Fedora:")
    print("  sudo dnf install git make gcc gcc-c++ bison flex zlib-devel gmp-devel mpfr-devel ncurses-devel xz-devel texinfo lzo-devel snappy-devel libzstd-devel")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Compile crash utility and pykdump extension.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                      # Build crash + all extensions (pykdump, trace, gcore...)
  %(prog)s --arch ARM64         # Build for ARM64 with extensions
  %(prog)s --without-pykdump    # Skip pykdump
  %(prog)s --without-extensions # Skip standard extensions (trace, gcore, etc)
  %(prog)s --pykdump-only       # Install pykdump only (skip crash build)
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
        "--version",
        default=PYKDUMP_COMPATIBLE_CRASH_VERSION,
        help=f"Crash version to build (default: {PYKDUMP_COMPATIBLE_CRASH_VERSION} for pykdump, or 'latest')",
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
    parser.add_argument(
        "--without-pykdump",
        action="store_true",
        help="Do NOT install pykdump extension",
    )
    parser.add_argument(
        "--pykdump-only",
        action="store_true",
        help="Only install pykdump (skip crash compilation)",
    )
    parser.add_argument(
        "--pykdump-from-source",
        action="store_true",
        help="Build pykdump from source (required for non-x86_64)",
    )
    parser.add_argument(
        "--without-extensions",
        action="store_true",
        help="Do NOT install standard extensions (trace, gcore, etc)",
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
    project_root = build_utils.get_project_root()
    install_dir = Path(args.install_dir) if args.install_dir else project_root / "bin"
    source_dir = Path(args.source_dir) if args.source_dir else project_root / "build" / "crash_src"
    
    # Common extensions directory
    ext_install_dir = project_root / "lib" / "crash" / "extensions"
    ext_install_dir.mkdir(parents=True, exist_ok=True)

    config = BuildConfig(
        arch=args.arch,
        version=args.version,
        install_dir=install_dir,
        source_dir=source_dir,
        clean=args.clean,
        jobs=args.jobs,
    )

    # Override version for pykdump compatibility
    should_install_pykdump = not args.without_pykdump or args.pykdump_only
    if should_install_pykdump and not args.pykdump_from_source and config.version == "latest":
        if config.arch.lower() in ["auto", "native", "x86_64", "amd64"]:
            logger.warning(f"Pykdump binaries only for crash 8.x, switching to {PYKDUMP_COMPATIBLE_CRASH_VERSION}")
            config.version = PYKDUMP_COMPATIBLE_CRASH_VERSION

    logger.info(f"Arch: {config.arch}, Version: {config.version}")

    # Build crash
    if not args.pykdump_only:
        result = build_crash(config)
        if result:
            print(f"\n✅ Crash: {result}")
        else:
            print("\n❌ Crash build failed")
            if args.without_pykdump:
                return 1

    # Install pykdump
    if should_install_pykdump:
        from crash_mcp.builder.install_pykdump import install_pykdump
        pykdump_result = install_pykdump(
            from_source=args.pykdump_from_source,
            crash_source_dir=source_dir if args.pykdump_from_source else None,
            force=args.clean,
            install_dir=ext_install_dir
        )
        if pykdump_result:
            print(f"✅ pykdump: {pykdump_result}")
        else:
            print("❌ pykdump failed")
            return 1
    
    # Install extensions
    if not args.without_extensions and not args.pykdump_only:
        from crash_mcp.builder.install_extensions import install_extensions
        installed = install_extensions(crash_src=source_dir, install_dir=ext_install_dir)
        if installed:
            print(f"✅ Extensions: {', '.join(installed)}")

    print("\n✅ Done!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
