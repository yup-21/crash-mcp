"""
Build scripts for crash utility and extensions.

This package contains scripts for:
- compile_crash: Compile crash utility from source
- install_pykdump: Install pykdump extension
- install_extensions: Install standard crash extensions
- utils: Shared utilities for build scripts
"""

from crash_mcp.builder.utils import get_project_root, check_dependencies, clone_or_update_repo
from crash_mcp.builder.utils import get_crash_version, checkout_version, get_latest_release_tag

__all__ = [
    'get_project_root',
    'check_dependencies', 
    'clone_or_update_repo',
    'get_crash_version',
    'checkout_version',
    'get_latest_release_tag',
]
