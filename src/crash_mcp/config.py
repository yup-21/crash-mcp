import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    SUPPRESS_MCP_WARNINGS = os.getenv("SUPPRESS_MCP_WARNINGS", "true").lower() == "true"

    # Crash Analysis specific (defaults)
    CRASH_SEARCH_PATH = os.getenv("CRASH_SEARCH_PATH", "/var/crash")
    
    # Extensions Configuration
    # Auto-load all extensions from CRASH_EXTENSION_PATH (true/false)
    CRASH_EXTENSION_LOAD = os.getenv("CRASH_EXTENSION_LOAD", "true").lower() == "true"
    # Extension search paths (colon-separated), maps to crash's CRASH_EXTENSIONS env var
    # Default includes project lib/crash/extensions
    CRASH_EXTENSION_PATH = os.getenv("CRASH_EXTENSION_PATH", "")


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

