import os
import logging
from mcp.server.fastmcp import FastMCP
from crash_mcp.config import Config

logger = logging.getLogger(__name__)

try:
    from importlib.resources import files
except ImportError:
    pass # Should adhere to python version > 3.9

SYSTEM_PROMPT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'docs', 'system_prompt.md')

def get_system_prompt() -> str:
    """Read the system prompt from package resources or fallback to doc file."""
    # Priority 1: Package Resource (Production / Install)
    try:
        return files('crash_mcp.resource').joinpath('system_prompt.md').read_text(encoding='utf-8')
    except Exception as e:
        logger.debug(f"Could not read system prompt from package resources: {e}")

    # Priority 2: Development Environment (Source Root)
    try:
        # Check absolute resolved path
        path = SYSTEM_PROMPT_PATH
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
                
        # Check CWD relative path
        if os.path.exists("docs/system_prompt.md"):
            with open("docs/system_prompt.md", 'r', encoding='utf-8') as f:
                return f.read()

        return "System prompt file not found."
    except Exception as e:
        logger.error(f"Failed to read system prompt: {e}")
        return f"Error reading system prompt: {str(e)}"

def register(mcp: FastMCP):
    """Register prompts with MCP server."""
    
    @mcp.prompt()
    def analysis_prompt() -> str:
        """Standard System Prompt for Crash Analysis Expert Role."""
        return get_system_prompt()
