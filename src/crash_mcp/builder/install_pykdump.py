#!/usr/bin/env python3
"""
PyKdump Extension Installer

Downloads and installs the pykdump extension (mpykdump.so) for the crash utility.
Supports both pre-built binaries (x86_64) and source compilation.

Usage:
    python -m crash_mcp.install_pykdump
    python -m crash_mcp.install_pykdump --from-source
    python -m crash_mcp.install_pykdump --crash-version 8
"""
import os
import sys
import shutil
import tarfile
import logging
import argparse
import subprocess
import tempfile
import re
import urllib.request
import multiprocessing
from pathlib import Path
from typing import Optional, Tuple

from crash_mcp.builder import utils as build_utils

logger = logging.getLogger(__name__)

# SourceForge URLs
PYKDUMP_BASE_URL = "https://sourceforge.net/projects/pykdump/files"
PYKDUMP_GIT_URL = "https://git.code.sf.net/p/pykdump/code"
PYKDUMP_VERSION = "3.9.1"

# Build dependencies
BUILD_DEPENDENCIES = {
    "binaries": ["git", "make", "gcc"],
    "apt_packages": [
        "git", "make", "gcc", "g++", "python3-dev", 
        "zlib1g-dev", "libncurses-dev", "liblzma-dev"
    ],
}


# Use centralized get_project_root from build_utils
get_project_root = build_utils.get_project_root


def detect_crash_version() -> Optional[int]:
    """Detect the major version of installed crash utility."""
    crash_bin = shutil.which("crash")
    if not crash_bin:
        project_bin = get_project_root() / "bin"
        for crash_path in [project_bin / "crash", project_bin / "crash-arm64"]:
            if crash_path.exists():
                crash_bin = str(crash_path)
                break
    
    if not crash_bin:
        return None
    
    try:
        result = subprocess.run(
            [crash_bin, "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        version_line = result.stdout.strip().split('\n')[0]
        if "crash" in version_line.lower():
            parts = version_line.split()
            for part in parts:
                if part[0].isdigit():
                    return int(part.split('.')[0])
    except Exception as e:
        logger.debug(f"Failed to detect crash version: {e}")
    
    return None


def find_crash_source() -> Optional[Path]:
    """Find crash source directory for building pykdump."""
    # Check project build directory first
    project_crash = get_project_root() / "build" / "crash_src"
    if (project_crash / "defs.h").exists():
        return project_crash
    
    # Check common locations
    common_paths = [
        Path.home() / "crash",
        Path("/usr/src/crash"),
        Path("/opt/crash"),
    ]
    for path in common_paths:
        if (path / "defs.h").exists():
            return path
    
    return None


def clone_pykdump_source(dest_dir: Path) -> bool:
    """Clone pykdump source code."""
    return build_utils.clone_or_update_repo(PYKDUMP_GIT_URL, dest_dir)


def build_pykdump_from_source(
    source_dir: Path,
    crash_source_dir: Path,
    install_dir: Path,
    jobs: int = 0
) -> Optional[Path]:
    """
    Build pykdump from source.
    
    Args:
        source_dir: pykdump source directory
        crash_source_dir: crash utility source directory (needed for headers)
        install_dir: Where to install mpykdump.so
        jobs: Number of parallel jobs (0 = auto)
        
    Returns:
        Path to installed mpykdump.so, or None if build failed.
    """
    if jobs == 0:
        jobs = multiprocessing.cpu_count()
    
    # Resolve paths to absolute
    source_dir = source_dir.resolve()
    crash_source_dir = crash_source_dir.resolve()
    
    logger.info(f"Building pykdump from source...")
    logger.info(f"  Source: {source_dir}")
    logger.info(f"  Crash source: {crash_source_dir}")
    logger.info(f"  Jobs: {jobs}")
    
    # Set environment for build
    env = os.environ.copy()
    env["CRASHDIR"] = str(crash_source_dir)
    # Build in Extension subdirectory
    ext_dir = source_dir / "Extension"
    if not ext_dir.exists():
        logger.error(f"Extension directory not found in {source_dir}")
        return None

    # Patch pyconf.py to support installed python/venv
    pyconf = ext_dir / "pyconf.py"
    if pyconf.exists():
        logger.info("Patching pyconf.py for system python...")
        content = pyconf.read_text()
        # Fix python_buildir to point to LIBDIR instead of executable dir
        # This fixes determining pyliba path
        content = content.replace(
            "python_buildir =  os.path.dirname(python_exe)",
            "python_buildir = get_config_var('LIBDIR')"
        )
        # Remove distutils import for Python 3.12+
        content = content.replace(
            "from distutils.core import setup, Extension",
            "#from distutils.core import setup, Extension"
        )
        # Fix pyliba to use shared library (LDLIBRARY) if available, to avoid -fPIC issues
        content = content.replace(
            "pyliba =  os.path.join(python_buildir, get_config_var('LIBRARY'))",
            "pyliba =  os.path.join(python_buildir, get_config_var('LDLIBRARY') or get_config_var('LIBRARY'))"
        )
        # Fix stdlib path to use get_path('stdlib') instead of source dir assumption
        content = content.replace(
            "stdlib = os.path.join(python_srcdir, 'Lib')",
            "stdlib = get_path('stdlib')"
        )
        # Ensure -fPIC is used for compilation (needed for shared object)
        content = content.replace(
            "cflags = get_config_var('CFLAGS')",
            "cflags = get_config_var('CFLAGS') + ' -fPIC'"
        )
        pyconf.write_text(content)

    # Patch epython.c for Python 3.11+ (remove deprecated headers)
    epyc = ext_dir / "epython.c"
    if epyc.exists():
        logger.info("Patching epython.c for Python 3.11+...")
        content = epyc.read_text()
        # Add _GNU_SOURCE for struct option
        if "#define _GNU_SOURCE" not in content:
            content = "#define _GNU_SOURCE\n" + content
        # Use // for comments to avoid nested /* */ errors
        content = content.replace("#include <eval.h>", "// #include <eval.h>")
        content = content.replace("#include <compile.h>", "// #include <compile.h>")
        epyc.write_text(content)

    # Ensure minpylib list exists for current python version
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
    minpylib = ext_dir / f"minpylib-{py_ver}.lst"
    if not minpylib.exists():
        # Fallback to 3.10 if available, or any latest
        logger.info(f"Creating missing {minpylib.name} from 3.10 template...")
        src_lst = ext_dir / "minpylib-3.10.lst"
        if src_lst.exists():
             shutil.copy(src_lst, minpylib)
             # Patch minpylib for 3.12 differences
             if py_ver == "3.12":
                 lst_content = minpylib.read_text()
                 # re.py became a package 're', list individual files
                 re_files = "\\nre/__init__.py\\nre/_casefix.py\\nre/_compiler.py\\nre/_constants.py\\nre/_parser.py"
                 lst_content = re.sub(r'^\s*re\.py\s*$', re_files, lst_content, flags=re.MULTILINE)
                 
                 # Add threading.py which seems missing
                 if "threading.py" not in lst_content:
                     lst_content += "\nthreading.py"
                 
                 minpylib.write_text(lst_content)

    # Patch Makefile to add -fPIC for shared library building
    # Note: zip is now available via system package, no longer need zip_helper.py
    mkfile = ext_dir / "Makefile"
    if mkfile.exists():
        logger.info("Patching Makefile for -fPIC compilation...")
        mk = mkfile.read_text()
        
        # Inject -fPIC into CFLAGS in Makefile (needed for shared object)
        if "-fPIC" not in mk:
            mk = re.sub(r'^(BASE_CFLAGS\s*:=\s*\$\(CFLAGS\).*)$', r'\1 -fPIC', mk, flags=re.MULTILINE)
            mkfile.write_text(mk)


    # Configure (run pyconf.py directly)
    try:
        logger.info("Configuring pykdump (via pyconf.py)...")
        # Run using current python interpreter
        subprocess.run(
            [sys.executable, "pyconf.py", f"--crashdir={crash_source_dir}"],
            cwd=ext_dir,
            env=env,
            check=True
        )
    except subprocess.CalledProcessError as e:
        logger.error(f"Configure failed: {e}")
        return None

    # Run make
    try:
        # Build with -j1 to avoid race conditions with custom zip helper and file generation
        logger.info("Building PyKdump extension (single-threaded for reliability)...")
        subprocess.run(
            ["make", "-j1"],
            cwd=ext_dir,
            check=True
        )
    except subprocess.CalledProcessError as e:
        logger.error(f"Build failed: {e}")
        return None
    
    # Find the built .so file
    so_files = list(ext_dir.glob("mpykdump*.so"))
    
    if not so_files:
        logger.error("Build completed but mpykdump.so not found")
        return None
    
    # Install
    install_dir.mkdir(parents=True, exist_ok=True)
    target_file = install_dir / "mpykdump.so"
    
    try:
        shutil.copy2(so_files[0], target_file)
        target_file.chmod(0o755)
        logger.info(f"Successfully installed: {target_file}")
        return target_file
    except Exception as e:
        logger.error(f"Failed to install: {e}")
        return None


def download_file(url: str, dest: Path) -> bool:
    """Download a file from URL."""
    logger.info(f"Downloading from: {url}")
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            with open(dest, 'wb') as f:
                shutil.copyfileobj(response, f)
        return True
    except Exception as e:
        logger.error(f"Download failed: {e}")
        return False


def get_writable_install_path() -> Path:
    """Get a writable installation path, preferring project-local paths."""
    # Prefer project-local path first
    project_lib = get_project_root() / "lib"
    user_paths = [
        project_lib,  # ./lib (project-local, first priority)
        Path.home() / ".crash" / "extensions",
    ]
    
    # System paths (need root)
    system_paths = [
        Path("/usr/lib64/crash/extensions"),
        Path("/usr/lib/crash/extensions"),
    ]
    
    # Try user paths first
    for path in user_paths:
        try:
            path.mkdir(parents=True, exist_ok=True)
            if os.access(path, os.W_OK):
                return path
        except PermissionError:
            continue
    
    # Try system paths
    for path in system_paths:
        if path.exists() and os.access(path, os.W_OK):
            return path
    
    # Fallback to user home
    fallback = Path.home() / ".crash" / "extensions"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def install_from_binary(
    crash_version: int,
    install_dir: Path,
    force: bool = False
) -> Optional[Path]:
    """Install pykdump from pre-built binary."""
    target_file = install_dir / "mpykdump.so"
    
    if target_file.exists() and not force:
        logger.info(f"pykdump already installed at: {target_file}")
        logger.info("Use --force to reinstall.")
        return target_file
    
    download_url = f"{PYKDUMP_BASE_URL}/mpykdump-x86_64/mpykdump-{PYKDUMP_VERSION}-crash{crash_version}.so/download"
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_file = Path(tmpdir) / f"mpykdump-crash{crash_version}.so"
        
        if not download_file(download_url, tmp_file):
            return None
        
        try:
            install_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(tmp_file, target_file)
            target_file.chmod(0o755)
            logger.info(f"Successfully installed: {target_file}")
            return target_file
        except Exception as e:
            logger.error(f"Failed to install: {e}")
            return None


def install_pykdump(
    crash_version: Optional[int] = None,
    install_dir: Optional[Path] = None,
    from_source: bool = False,
    crash_source_dir: Optional[Path] = None,
    force: bool = False
) -> Optional[Path]:
    """
    Install pykdump extension.
    
    Args:
        crash_version: Major crash version (7 or 8). Auto-detected if None.
        install_dir: Installation directory. Auto-detected if None.
        from_source: If True, build from source instead of downloading binary.
        crash_source_dir: Path to crash source (required for source build).
        force: Force reinstall even if already exists.
        
    Returns:
        Path to installed mpykdump.so, or None if installation failed.
    """
    # Detect crash version
    if crash_version is None:
        crash_version = detect_crash_version()
        if crash_version is None:
            logger.warning("Could not detect crash version. Defaulting to crash 8.")
            crash_version = 8
        else:
            logger.info(f"Detected crash version: {crash_version}")
    
    # Determine installation directory
    if install_dir is None:
        install_dir = get_writable_install_path()
    else:
        install_dir = Path(install_dir)
    
    logger.info(f"Installation directory: {install_dir}")
    
    if from_source:
        # Source build path
        if crash_source_dir is None:
            crash_source_dir = find_crash_source()
            if crash_source_dir is None:
                logger.error("Crash source directory not found.")
                logger.error("Build crash first with: python -m crash_mcp.compile_crash")
                logger.error("Or specify --crash-source-dir")
                return None
        
        pykdump_source = get_project_root() / "build" / "pykdump_src"
        if not clone_pykdump_source(pykdump_source):
            return None
        
        return build_pykdump_from_source(
            pykdump_source, 
            Path(crash_source_dir), 
            install_dir
        )
    else:
        # Binary download path
        if crash_version not in [7, 8]:
            logger.error(f"Pre-built binaries only available for crash 7 or 8, not {crash_version}")
            logger.info("Try --from-source for other versions")
            return None
        
        return install_from_binary(crash_version, install_dir, force)


def print_usage_instructions(install_path: Path):
    """Print usage instructions after installation."""
    print("\n" + "=" * 60)
    print("PYKDUMP INSTALLATION COMPLETE")
    print("=" * 60)
    print(f"\nInstalled to: {install_path}")
    print("\n--- Manual Usage in crash ---")
    print(f"  crash> extend {install_path}")
    print("  crash> epython your_script.py")
    print("\n--- Auto-load on startup ---")
    print(f"  echo 'extend {install_path}' >> ~/.crashrc")
    print("\n--- With crash-mcp ---")
    print("  Set environment variable:")
    print("    export CRASH_EXTENSION_LOAD=mpykdump,trace,...")
    print("=" * 60 + "\n")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Download and install pykdump extension for crash utility.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Download pre-built binary (x86_64)
  %(prog)s --from-source            # Build from source
  %(prog)s --crash-version 8        # Specify crash version
  %(prog)s --install-dir ~/.crash/extensions  # Custom install location

Notes:
  - Pre-built binaries are only available for x86_64.
  - Use --from-source for ARM64 or other architectures.
  - Source build requires crash source (run compile_crash.py first).
        """,
    )
    parser.add_argument(
        "--crash-version", "-c",
        type=int,
        choices=[7, 8],
        default=None,
        help="Major crash version (7 or 8). Auto-detected if not specified.",
    )
    parser.add_argument(
        "--install-dir", "-i",
        default=None,
        help="Installation directory. Defaults to ~/.crash/extensions",
    )
    parser.add_argument(
        "--from-source", "-s",
        action="store_true",
        help="Build from source instead of downloading pre-built binary.",
    )
    parser.add_argument(
        "--crash-source-dir",
        default=None,
        help="Path to crash source directory (for source build).",
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Force reinstall even if already exists.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output.",
    )

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    install_dir = Path(args.install_dir) if args.install_dir else None
    crash_source = Path(args.crash_source_dir) if args.crash_source_dir else None
    
    result = install_pykdump(
        crash_version=args.crash_version,
        install_dir=install_dir,
        from_source=args.from_source,
        crash_source_dir=crash_source,
        force=args.force
    )
    
    if result:
        print_usage_instructions(result)
        return 0
    else:
        print("\n❌ Installation failed. Check the logs above for details.")
        if not args.from_source:
            print("\nTry building from source:")
            print("  python -m crash_mcp.install_pykdump --from-source")
        return 1


if __name__ == "__main__":
    sys.exit(main())
