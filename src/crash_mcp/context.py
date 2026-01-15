"""Global state for crash-mcp server."""
from typing import Dict, Optional
from crash_mcp.common.session import BaseSession

# Session storage
sessions: Dict[str, BaseSession] = {}
last_session_id: Optional[str] = None
