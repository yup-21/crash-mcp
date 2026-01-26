"""Global state for crash-mcp server."""
import atexit
import logging
from typing import Dict, Optional
from crash_mcp.common.base_session import BaseSession
from crash_mcp.common.session_manager import SessionManager
from crash_mcp.config import Config

logger = logging.getLogger("crash-mcp")

# Session manager (singleton) - handles deduplication and workdir
session_manager = SessionManager(Config.SESSION_WORKDIR_BASE)

# Session storage (UnifiedSession instances)
sessions: Dict[str, BaseSession] = {}
last_session_id: Optional[str] = None


def _cleanup_sessions():
    """Clean up all active sessions on exit."""
    global sessions, last_session_id
    if sessions:
        logger.info(f"Cleaning up {len(sessions)} active session(s)...")
        for session_id, session in list(sessions.items()):
            try:
                if session.is_active():
                    session.close()
                    logger.info(f"Session {session_id} closed.")
                session_manager.remove_session(session_id)  # Sync with session_manager
            except Exception as e:
                logger.warning(f"Error closing session {session_id}: {e}")
        sessions.clear()
        last_session_id = None


# Register cleanup handler
atexit.register(_cleanup_sessions)
