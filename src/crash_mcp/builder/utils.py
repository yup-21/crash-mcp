#!/usr/bin/env python3
"""
Shared utilities for crash build scripts.

Provides common functions used by compile_crash.py, install_pykdump.py,
and install_extensions.py.
"""
import os
import shutil
import subprocess
import logging
from pathlib import Path
from typing import Optional, Tuple, List

logger = logging.getLogger(__name__)


def get_project_root() -> Path:
    """Get the project root directory by finding pyproject.toml."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "pyproject.toml").exists():
            return current
        current = current.parent
    # Fallback to current working directory
    return Path.cwd()


def check_dependencies(binaries: List[str]) -> Tuple[bool, List[str]]:
    """
    Check if required binary dependencies are available.
    
    Returns:
        Tuple of (all_ok, missing_list)
    """
    missing = []
    for tool in binaries:
        if not shutil.which(tool):
            missing.append(tool)
    return len(missing) == 0, missing


def clone_or_update_repo(url: str, dest_dir: Path, branch: Optional[str] = None) -> bool:
    """
    Clone a git repository or update if it already exists.
    
    Args:
        url: Git repository URL
        dest_dir: Destination directory
        branch: Optional branch/tag to checkout after clone
        
    Returns:
        True if successful, False otherwise
    """
    git_dir = dest_dir / ".git"
    
    if git_dir.exists():
        logger.info(f"Updating existing repository in {dest_dir}...")
        try:
            subprocess.run(
                ["git", "fetch", "--tags"],
                cwd=dest_dir,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "pull"],
                cwd=dest_dir,
                check=True,
                capture_output=True,
            )
            return True
        except subprocess.CalledProcessError as e:
            logger.warning(f"Git update failed: {e.stderr.decode() if e.stderr else e}")
            logger.info("Continuing with existing source...")
            return True
    else:
        logger.info(f"Cloning repository from {url}...")
        dest_dir.parent.mkdir(parents=True, exist_ok=True)
        try:
            cmd = ["git", "clone", url, str(dest_dir)]
            subprocess.run(cmd, check=True)
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to clone repository: {e}")
            return False


def get_latest_release_tag(source_dir: Path) -> Optional[str]:
    """
    Get the latest release tag from a git repository.
    
    Returns version number like "9.0.1" or None if not found.
    """
    try:
        result = subprocess.run(
            ["git", "tag", "--sort=-version:refname"],
            cwd=source_dir,
            check=True,
            capture_output=True,
            text=True
        )
        tags = result.stdout.strip().split('\n')
        # Filter for proper version tags (start with digit or common prefix)
        for tag in tags:
            tag = tag.strip()
            # Skip tags like "crash-7.0.5", prefer plain version numbers
            if tag and tag[0].isdigit():
                return tag
        # Fall back to crash-X.X.X format
        for tag in tags:
            if tag.startswith("crash-"):
                return tag.replace("crash-", "")
        return tags[0] if tags else None
    except subprocess.CalledProcessError:
        return None


def get_crash_version(source_dir: Path) -> Optional[str]:
    """
    Get the current crash version from source directory.
    
    Returns version string like "9.0.1" or None if not found.
    """
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            cwd=source_dir,
            check=True,
            capture_output=True,
            text=True
        )
        tag = result.stdout.strip()
        # Handle "crash-X.X.X" format
        if tag.startswith("crash-"):
            return tag.replace("crash-", "")
        return tag
    except subprocess.CalledProcessError:
        return None


def checkout_version(source_dir: Path, version: str) -> bool:
    """
    Checkout a specific version (tag) in the repository.
    
    Args:
        source_dir: Git repository directory
        version: Version string (e.g., "9.0.1" or "latest")
        
    Returns:
        True if successful
    """
    if version == "latest":
        target_tag = get_latest_release_tag(source_dir)
        if not target_tag:
            logger.warning("Could not determine latest release, using current HEAD")
            return True
        version = target_tag
    
    # Try plain version first, then with "crash-" prefix
    tags_to_try = [version, f"crash-{version}"]
    
    for tag in tags_to_try:
        try:
            subprocess.run(
                ["git", "checkout", tag],
                cwd=source_dir,
                check=True,
                capture_output=True,
            )
            logger.info(f"Checked out version: {tag}")
            return True
        except subprocess.CalledProcessError:
            continue
    
    logger.error(f"Version {version} not found in repository")
    return False


def get_crash_major_version(source_dir: Path) -> Optional[int]:
    """Get major version number (e.g., 9 for "9.0.1")."""
    version = get_crash_version(source_dir)
    if version:
        try:
            return int(version.split('.')[0])
        except (ValueError, IndexError):
            pass
    return None
