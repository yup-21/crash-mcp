"""Output pagination and search tools for crash-mcp."""
import logging
from typing import Optional
from mcp.server.fastmcp import FastMCP

from crash_mcp.tools.utils import json_response, get_session

logger = logging.getLogger("crash-mcp")


def get_command_output(command_id: str, offset: int = 0, limit: int = 50, 
               session_id: Optional[str] = None) -> str:
    """Fetch lines from a command output by offset and limit.
    
    Use this to paginate through long command outputs that were truncated.
    """
    try:
        target_id, session = get_session(session_id)
    except ValueError as e:
        return json_response("error", error=str(e))
    
    if not session.command_store:
        return json_response("error", error="Command store not available for this session.")
    
    # Clamp limit to max 500
    limit = min(limit, 500)
    
    try:
        text, count, total, has_more = session.command_store.get_lines(
            command_id, offset, limit
        )
        
        return json_response("success", {
            "output": text,
            "command_id": command_id,
            "state": {
                "total_lines": total,
                "offset": offset,
                "returned_lines": count,
                "has_more": has_more,
            }
        })
    except ValueError as e:
        return json_response("error", error=str(e))
    except Exception as e:
        logger.error(f"Error in get_command_output: {e}")
        return json_response("error", error=str(e))


def search_command_output(command_id: str, query: str, context_lines: int = 3,
                  session_id: Optional[str] = None) -> str:
    """Search within command output using regex pattern.
    
    Returns matching lines with surrounding context.
    """
    try:
        target_id, session = get_session(session_id)
    except ValueError as e:
        return json_response("error", error=str(e))
    
    if not session.command_store:
        return json_response("error", error="Command store not available for this session.")
    
    try:
        matches = session.command_store.search(command_id, query, context_lines)
        
        return json_response("success", {
            "matches": matches,
            "total_matches": len(matches),
            "command_id": command_id,
        })
    except ValueError as e:
        return json_response("error", error=str(e))
    except Exception as e:
        logger.error(f"Error in search_command_output: {e}")
        return json_response("error", error=str(e))


def register(mcp: FastMCP):
    """Register output tools with MCP server."""
    from crash_mcp.tools.tool_logging import logged_tool
    
    mcp.tool()(logged_tool(get_command_output))
    mcp.tool()(logged_tool(search_command_output))
