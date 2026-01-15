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
    base_prompt = ""
    
    # Priority 1: Package Resource (Production / Install)
    try:
        base_prompt = files('crash_mcp.resource').joinpath('system_prompt.md').read_text(encoding='utf-8')
    except Exception as e:
        logger.debug(f"Could not read system prompt from package resources: {e}")

    # Priority 2: Development Environment (Source Root)
    if not base_prompt:
        try:
            # Check absolute resolved path
            path = SYSTEM_PROMPT_PATH
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    base_prompt = f.read()
                    
            # Check CWD relative path
            elif os.path.exists("docs/system_prompt.md"):
                with open("docs/system_prompt.md", 'r', encoding='utf-8') as f:
                    base_prompt = f.read()
            else:
                base_prompt = "System prompt file not found."
        except Exception as e:
            logger.error(f"Failed to read system prompt: {e}")
            base_prompt = f"Error reading system prompt: {str(e)}"
    
    # Script resources removed from system prompt - now provided via skill resources
    
    return base_prompt

def register(mcp: FastMCP):
    """Register prompts with MCP server."""
    
    @mcp.prompt()
    def analysis_prompt() -> str:
        """Standard System Prompt for Crash Analysis Expert Role."""
        return get_system_prompt()
