"""Session lifecycle and deduplication management."""
import hashlib
import uuid
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple
from dataclasses import dataclass, field

from crash_mcp.config import Config

logger = logging.getLogger(__name__)


@dataclass
class SessionInfo:
    """Session metadata."""
    session_id: str
    vmcore_md5: str          # First 16 hex chars
    vmcore_path: str
    vmlinux_path: str
    workdir: Path
    context: Dict[str, str] = field(default_factory=dict)  # pid, cpu, etc.
    ref_count: int = 0  # Reference counting for shared sessions


class SessionManager:
    """Manages session lifecycle with deduplication by vmcore MD5."""
    
    # Crash commands that depend on context
    CONTEXT_DEPENDENT_COMMANDS = {"bt", "task", "vm", "vtop", "ptov", "rd", "wr"}
    
    # Context keys that can be set
    CONTEXT_KEYS = {"pid", "cpu", "context"}
    
    def __init__(self, base_workdir: str = None):
        self._base_workdir = Path(base_workdir or Config.SESSION_WORKDIR_BASE)
        self._base_workdir.mkdir(parents=True, exist_ok=True)
        
        self._sessions: Dict[str, SessionInfo] = {}     # session_id -> info
        self._vmcore_map: Dict[str, str] = {}           # vmcore_md5 -> session_id
        
        logger.info(f"SessionManager initialized with workdir: {self._base_workdir}")
        
    def get_or_create(self, vmcore_path: str, vmlinux_path: str = None) -> Tuple[str, SessionInfo, bool]:
        """Return (session_id, info, is_new). Dedup by vmcore MD5."""
        vmcore_md5 = self._compute_md5(vmcore_path)
        
        # Check if session already exists for this vmcore
        if vmcore_md5 in self._vmcore_map:
            sid = self._vmcore_map[vmcore_md5]
            logger.info(f"Reusing existing session {sid} for vmcore MD5 {vmcore_md5}")
            return sid, self._sessions[sid], False
        
        # Create new session
        sid = str(uuid.uuid4())
        workdir = self._base_workdir / vmcore_md5
        workdir.mkdir(parents=True, exist_ok=True)
        
        info = SessionInfo(
            session_id=sid,
            vmcore_md5=vmcore_md5,
            vmcore_path=vmcore_path,
            vmlinux_path=vmlinux_path or "",
            workdir=workdir,
            context={},
            ref_count=0,
        )
        self._sessions[sid] = info
        self._vmcore_map[vmcore_md5] = sid
        
        logger.info(f"Created new session {sid} for vmcore MD5 {vmcore_md5}, workdir: {workdir}")
        return sid, info, True
    
    def acquire(self, session_id: str) -> bool:
        """Increment reference count. Returns True if session exists."""
        if session_id in self._sessions:
            self._sessions[session_id].ref_count += 1
            logger.debug(f"Session {session_id} acquired, ref_count={self._sessions[session_id].ref_count}")
            return True
        return False
    
    def release(self, session_id: str) -> int:
        """Decrement reference count. Returns new count (-1 if not found)."""
        if session_id not in self._sessions:
            return -1
        self._sessions[session_id].ref_count -= 1
        count = self._sessions[session_id].ref_count
        logger.debug(f"Session {session_id} released, ref_count={count}")
        return count
    
    def get_ref_count(self, session_id: str) -> int:
        """Get current reference count."""
        if session_id in self._sessions:
            return self._sessions[session_id].ref_count
        return 0
    
    def get_session(self, session_id: str) -> Optional[SessionInfo]:
        """Get session info by ID."""
        return self._sessions.get(session_id)
    
    def update_context(self, session_id: str, key: str, value: str):
        """Update session context (e.g., after 'set pid 1234')."""
        if session_id in self._sessions:
            self._sessions[session_id].context[key] = value
            logger.debug(f"Session {session_id} context updated: {key}={value}")
    
    def get_context(self, session_id: str) -> Dict[str, str]:
        """Get current session context."""
        info = self._sessions.get(session_id)
        if info:
            return info.context.copy()
        return {}
    
    def get_relevant_context(self, session_id: str, command: str) -> Dict[str, str]:
        """Get context relevant to a command (for command_id generation).
        
        Only context-dependent commands (bt, task, etc.) include context in their ID.
        """
        cmd_word = command.strip().split()[0] if command.strip() else ""
        if cmd_word not in self.CONTEXT_DEPENDENT_COMMANDS:
            return {}
        return self.get_context(session_id)
    
    def parse_and_update_context(self, session_id: str, engine: str, command: str):
        """Parse command for context changes (e.g., 'set pid 1234')."""
        if engine != "crash":
            return
        
        parts = command.strip().split()
        if len(parts) >= 3 and parts[0] == "set":
            key = parts[1]
            value = parts[2]
            if key in self.CONTEXT_KEYS:
                self.update_context(session_id, key, value)
    
    def remove_session(self, session_id: str):
        """Remove session from registry."""
        if session_id in self._sessions:
            info = self._sessions[session_id]
            del self._vmcore_map[info.vmcore_md5]
            del self._sessions[session_id]
            logger.info(f"Removed session {session_id}")
    
    def _compute_md5(self, path: str) -> str:
        """Compute vmcore MD5 (first 64MB for speed)."""
        md5 = hashlib.md5()
        chunk_size = 64 * 1024 * 1024  # 64MB
        try:
            with open(path, 'rb') as f:
                data = f.read(chunk_size)
                md5.update(data)
            return md5.hexdigest()[:16]
        except IOError as e:
            logger.warning(f"Could not read vmcore for MD5: {e}")
            # Fallback to path hash
            return hashlib.md5(path.encode()).hexdigest()[:16]
