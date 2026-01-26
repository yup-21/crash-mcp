"""Common utilities for crash-mcp tools."""
import json
import logging
from typing import Optional, Tuple

import crash_mcp.context as context
from crash_mcp.common.unified_session import UnifiedSession

logger = logging.getLogger("crash-mcp")


def json_response(status: str, result=None, error=None) -> str:
    """Format JSON response for tool output."""
    response = {"status": status}
    if result is not None:
        response["result"] = result
    if error is not None:
        response["error"] = error
    return json.dumps(response, ensure_ascii=False)


def get_session(session_id: Optional[str] = None) -> Tuple[str, UnifiedSession]:
    """Get session by ID or use last session.
    
    Args:
        session_id: Optional session ID. If None, uses last_session_id.
        
    Returns:
        Tuple of (session_id, session)
        
    Raises:
        ValueError: If session not found or not active.
    """
    target_id = session_id or context.last_session_id
    
    if not target_id:
        raise ValueError("No session specified and no active default session.")
    
    if target_id not in context.sessions:
        raise ValueError(f"Session ID {target_id} not found.")
    
    session = context.sessions[target_id]
    if not session.is_active():
        del context.sessions[target_id]
        context.session_manager.remove_session(target_id)  # Sync with session_manager
        raise ValueError("Session is no longer active.")
    
    return target_id, session
