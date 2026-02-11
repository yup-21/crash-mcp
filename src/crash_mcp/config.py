import os

# Load environment variables from .env file (optional)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional

class Config:
    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_TOOL_CALLS = os.getenv("LOG_TOOL_CALLS", "true").lower() == "true"
    SUPPRESS_MCP_WARNINGS = os.getenv("SUPPRESS_MCP_WARNINGS", "true").lower() == "true"

    # Crash Analysis specific (defaults)
    CRASH_SEARCH_PATH = os.getenv("CRASH_SEARCH_PATH", "/var/crash")
    
    # Extensions Configuration
    # Auto-load all extensions from CRASH_EXTENSION_PATH (true/false)
    CRASH_EXTENSION_LOAD = os.getenv("CRASH_EXTENSION_LOAD", "true").lower() == "true"
    # Extension search paths (colon-separated), maps to crash's CRASH_EXTENSIONS env var
    # Default includes project lib/crash/extensions
    CRASH_EXTENSION_PATH = os.getenv("CRASH_EXTENSION_PATH", "")
    
    # Output Pagination
    OUTPUT_TRUNCATE_LINES = int(os.getenv("CRASH_MCP_TRUNCATE_LINES", "2000"))
    
    # Session Workdir Base
    SESSION_WORKDIR_BASE = os.getenv("CRASH_MCP_WORKDIR", "/tmp/crash-mcp-sessions")
    
    # Command Cache Mode: disable / normal / force
    #   disable - no caching, always re-execute
    #   normal  - only cache commands that were persisted to disk (large/slow outputs)
    #   force   - cache all commands including small/fast ones in memory
    COMMAND_CACHE_MODE = os.getenv("CRASH_MCP_CACHE", "normal").lower()
    if COMMAND_CACHE_MODE not in ("disable", "normal", "force"):
        COMMAND_CACHE_MODE = "normal"
    
    # Command Persistence Threshold (seconds)
    # Only save output to disk if execution time exceeds this value or output is truncated
    COMMAND_SAVE_THRESHOLD_SECONDS = float(os.getenv("COMMAND_SAVE_THRESHOLD_SECONDS", "2.0"))

    # External Tools
    GET_DUMPINFO_SCRIPT = os.getenv("GET_DUMPINFO_SCRIPT", "")
    
    # Crash Binary Path (directory containing crash, crash-arm64, etc.)
    CRASH_PATH = os.getenv("CRASH_PATH", "")
    
    # External Scripts Path (colon-separated)
    # Scripts in these directories are auto-discovered by run_analysis_script
    DRGN_SCRIPTS_PATH = os.getenv("DRGN_SCRIPTS_PATH", "")


def get_extension_paths() -> list:
    """Get list of extension search paths for crash extensions."""
    from pathlib import Path
    paths = []
    
    # 1. User-configured paths (highest priority)
    if Config.CRASH_EXTENSION_PATH:
        paths.extend(p.strip() for p in Config.CRASH_EXTENSION_PATH.split(":") if p.strip())
    
    # 2. Project lib/crash/extensions (relative to this file: config.py -> crash_mcp -> src -> project)
    project_root = Path(__file__).resolve().parent.parent.parent
    project_ext = project_root / "lib" / "crash" / "extensions"
    if project_ext.exists():
        paths.append(str(project_ext))
    
    # 3. User home ~/.crash/extensions
    user_ext = Path.home() / ".crash" / "extensions"
    if user_ext.exists():
        paths.append(str(user_ext))
    
    return paths 

