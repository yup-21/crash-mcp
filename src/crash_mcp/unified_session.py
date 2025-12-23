import logging
import uuid
from typing import Optional

from crash_mcp.session import CrashSession
from crash_mcp.drgn_session import DrgnSession

logger = logging.getLogger(__name__)

class UnifiedSession:
    """
    Manages both CrashSession and DrgnSession, automatically routing commands.
    """
    def __init__(self, dump_path: str, kernel_path: str = None, 
                 remote_host: str = None, remote_user: str = None):
        self.dump_path = dump_path
        self.kernel_path = kernel_path
        self.remote_host = remote_host
        self.remote_user = remote_user
        
        # Initialize sub-sessions
        # They are lazy-started conceptually, but we might as well start them together 
        # since "analyze_target" usually implies ready-to-go.
        self.crash_session = CrashSession(dump_path, kernel_path, 
                                        remote_host=remote_host, remote_user=remote_user)
        self.drgn_session = DrgnSession(dump_path, kernel_path, 
                                        remote_host=remote_host, remote_user=remote_user)
        
        self.id = str(uuid.uuid4())

    def start(self, timeout: int = 30):
        """
        Starts both sessions.
        """
        logger.info(f"Starting Unified Session {self.id}...")
        results = []
        
        # Start Crash
        try:
            self.crash_session.start(timeout=timeout)
            logger.info("Crash engine started.")
        except Exception as e:
            logger.error(f"Crash engine failed to start: {e}")
            self.crash_session = None # Mark unavailable
            
        # Start Drgn
        try:
            self.drgn_session.start(timeout=timeout)
            logger.info("Drgn engine started.")
        except Exception as e:
            logger.error(f"Drgn engine failed to start: {e}")
            self.drgn_session = None
            
        if self.crash_session is None and self.drgn_session is None:
            raise RuntimeError("Both engines failed to start.")

    def execute_command(self, command: str, timeout: int = 60, truncate: bool = True) -> str:
        """
        Routes the command to the appropriate engine.
        """
        cmd = command.strip()
        
        # Explicit routing prefix
        if cmd.startswith("drgn:"):
            return self._exec_drgn(cmd[5:].strip(), timeout, truncate)
        elif cmd.startswith("crash:"):
            return self._exec_crash(cmd[6:].strip(), timeout, truncate)

            
        # Heuristic Routing
        # Drgn is Python-based. Look for python syntax or known objects.
        is_drgn = False
        
        # Indicators of python/drgn code
        drgn_indicators = ['prog', 'libkdumpfile', 'find_task', '(', ')', '=', '.', '[', ']', '"', "'"]
        # Indicators of crash commands (simple words, known cmds)
        crash_cmds = ['sys', 'bt', 'ps', 'log', 'mount', 'net', 'dev', 'files', 'help', 'set', 'extend']
        
        first_word = cmd.split()[0] if cmd else ""
        
        if first_word in crash_cmds:
             is_drgn = False
        elif any(x in cmd for x in ['=', '(', '.', '[']):
            # Assignment, function call, attributes -> likely Python
            is_drgn = True
        elif first_word in ['prog', 'task', 'thread']:
            is_drgn = True
        else:
            # Default fallback to crash if ambiguous? Or try both?
            # Defaulting to crash is safer for system admins used to crash.
            is_drgn = False
            
        if is_drgn:
            return self._exec_drgn(cmd, timeout, truncate)
        else:
            return self._exec_crash(cmd, timeout, truncate)

    def _exec_drgn(self, cmd: str, timeout: int, truncate: bool) -> str:
        if not self.drgn_session or not self.drgn_session.is_active():
            return "Error: Drgn engine is not active."
        return self.drgn_session.execute_command(cmd, timeout, truncate)

    def _exec_crash(self, cmd: str, timeout: int, truncate: bool) -> str:
        if not self.crash_session or not self.crash_session.is_active():
             return "Error: Crash engine is not active."
        return self.crash_session.execute_command(cmd, timeout, truncate)

    def close(self):
        if self.crash_session:
            self.crash_session.close()
        if self.drgn_session:
            self.drgn_session.close()
            
    def is_active(self) -> bool:
        return (self.crash_session and self.crash_session.is_active()) or \
               (self.drgn_session and self.drgn_session.is_active())
