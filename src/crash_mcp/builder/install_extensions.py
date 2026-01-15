#!/usr/bin/env python3
"""
Crash Extensions Installer

Compiles and installs common crash extensions (trace, gcore, etc.)
from the official crash-utility/crash-extensions repository.

Usage:
    python -m crash_mcp.install_extensions --crash-src /path/to/crash/source
"""
import os
import sys
import shutil
import logging
import argparse
import subprocess
import multiprocessing
from pathlib import Path
from typing import List, Optional

from crash_mcp.builder import utils as build_utils

logger = logging.getLogger(__name__)

EXTENSIONS_REPO = "https://github.com/crash-utility/crash-extensions.git"

# List of extensions to build by default
DEFAULT_EXTENSIONS = [
    "trace",
    "snap",
    "dminfo",
]

# Use centralized utilities from build_utils
get_project_root = build_utils.get_project_root


def clone_extensions_repo(dest_dir: Path) -> bool:
    """Clone or update crash-extensions repository."""
    return build_utils.clone_or_update_repo(EXTENSIONS_REPO, dest_dir)

def patch_extension_source(ext_name: str, repo_dir: Path):
    """Patch extension source code to fix build issues."""
    pass

def build_extension(
    ext_name: str,
    repo_dir: Path,
    crash_src: Path,
    install_dir: Path
) -> bool:
    """Build a single extension."""
    src_file = repo_dir / f"{ext_name}.c"
    if not src_file.exists():
        logger.warning(f"Extension source not found: {src_file}")
        return False

    # Apply patches if needed
    patch_extension_source(ext_name, repo_dir)

    # Check for dedicated makefile
    mk_file = repo_dir / f"{ext_name}.mk"
    
    out_file = repo_dir / f"{ext_name}.so"
    
    logger.info(f"Building {ext_name}.so...")
    
    try:
        if mk_file.exists():
            # Use provided makefile
            cmd = ["make", "-f", f"{ext_name}.mk"]
            env = os.environ.copy()
            env["CRASH_INCLUDEDIR"] = str(crash_src)
            subprocess.run(cmd, cwd=repo_dir, env=env, check=True, capture_output=True)
        else:
            # Generic compilation
            # gcc -fPIC -shared -o name.so name.c -I...
            cmd = [
                "gcc", 
                "-fPIC", 
                "-shared", 
                "-o", str(out_file), 
                str(src_file),
                "-I", str(crash_src),
                "-Wall",
                "-nostartfiles"
            ]
            # Some extensions might need extra libs, handled poorly here but ok for basics
            subprocess.run(cmd, check=True)
            
        # Install
        install_dir.mkdir(parents=True, exist_ok=True)
        dest = install_dir / f"{ext_name}.so"
        shutil.copy2(out_file, dest)
        return True
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to build {ext_name}: {e}")
        return False

def install_extensions(
    crash_src: Path,
    install_dir: Path,
    extensions: List[str] = DEFAULT_EXTENSIONS
) -> List[str]:
    """
    Build and install extensions.
    Returns list of successfully installed extensions.
    """
    repo_dir = get_project_root() / "build" / "crash_extensions_src"
    
    if not clone_extensions_repo(repo_dir):
        return []

    success = []
    for ext in extensions:
        if build_extension(ext, repo_dir, crash_src, install_dir):
            success.append(ext)
            
    return success

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Simple CLI for testing/standalone usage
    parser = argparse.ArgumentParser()
    parser.add_argument("--crash-src", required=True, type=Path)
    parser.add_argument("--install-dir", required=True, type=Path)
    args = parser.parse_args()
    
    installed = install_extensions(args.crash_src, args.install_dir)
    print(f"Installed: {', '.join(installed)}")
