import logging
import uuid
from pathlib import Path
from typing import Optional, Dict, Tuple

from crash_mcp.crash.session import CrashSession
from crash_mcp.drgn.session import DrgnSession
from crash_mcp.common.command_store import CommandStore, CommandResult
from crash_mcp.config import Config

logger = logging.getLogger(__name__)


class UnifiedSession:
    """
    Manages both CrashSession and DrgnSession, automatically routing commands.
    Enhanced with workdir, context tracking, and persistent command storage.
    """
    
    # Commands that depend on context (pid, cpu)
    CONTEXT_DEPENDENT_COMMANDS = {"bt", "task", "vm", "vtop", "ptov", "rd", "wr"}
    
    # Context keys that can be set
    CONTEXT_KEYS = {"pid", "cpu", "context"}
    
    def __init__(self, dump_path: str, kernel_path: str = None, 
                 remote_host: str = None, remote_user: str = None,
                 crash_args: list = None, workdir: Path = None):
        self.dump_path = dump_path
        self.kernel_path = kernel_path
        self.remote_host = remote_host
        self.remote_user = remote_user
        self.crash_args = crash_args or []
        
        # NEW: Workdir and command store
        self.workdir = Path(workdir) if workdir else None
        self.context: Dict[str, str] = {}
        self.command_store = CommandStore(self.workdir) if self.workdir else None
        
        # Initialize sub-sessions
        self.crash_session = CrashSession(dump_path, kernel_path, 
                                        remote_host=remote_host, remote_user=remote_user,
                                        crash_args=self.crash_args)
        self.drgn_session = DrgnSession(dump_path, kernel_path, 
                                        remote_host=remote_host, remote_user=remote_user)
        
        self.id = str(uuid.uuid4())
        self.drgn_start_error = None
        self.crash_start_error = None

    from typing import Callable

    def start(self, timeout: int = 120, on_progress: Optional[Callable[[float, str], None]] = None):
        """Starts both sessions."""
        logger.info(f"Starting Unified Session {self.id}...")
        
        def report(p, msg):
            if on_progress:
                on_progress(p, msg)

        # Helper to scale progress for sub-sessions
        # range_start to range_end
        def make_sub_progress(range_start, range_end):
            if not on_progress:
                return None
            def sub_cb(p, msg):
                # Map p (0-100) to range
                scaled = range_start + (p / 100.0) * (range_end - range_start)
                # We can optionally prefix the message
                on_progress(scaled, msg)
            return sub_cb
        
        # Start Crash (0-50%)
        try:
            report(0, "Starting Crash engine...")
            cb = make_sub_progress(0, 50)
            self.crash_session.start(timeout=timeout, on_progress=cb)
            logger.info("Crash engine started.")
            
            # Initialize context with crash's default values for cache consistency
            try:
                default_ctx = self.crash_session.get_default_context()
                self.context.update(default_ctx)
                logger.info(f"Initialized context from crash defaults: {default_ctx}")
            except Exception as e:
                logger.warning(f"Failed to initialize context: {e}")
            
            report(50, "Crash engine ready")
        except Exception as e:
            logger.error(f"Crash engine failed to start: {e}")
            self.crash_session = None
            self.crash_start_error = str(e)
            
        # Start Drgn (50-100%)
        try:
            report(50, "Starting Drgn engine...")
            cb = make_sub_progress(50, 90)
            self.drgn_session.start(timeout=timeout, on_progress=cb)
            logger.info("Drgn engine started.")
            self.drgn_start_error = None
            report(90, "Drgn engine ready")
        except Exception as e:
            logger.error(f"Drgn engine failed to start: {e}")
            self.drgn_session = None
            self.drgn_start_error = str(e)
            
        if self.crash_session is None and self.drgn_session is None:
            raise RuntimeError("Both engines failed to start.")
            
        report(100, "Session initialization complete")

    def execute_command(self, command: str, timeout: int = 60, truncate: bool = True) -> str:
        """Routes the command to the appropriate engine. Returns raw output string."""
        cmd = command.strip()
        
        # Explicit routing prefix
        if cmd.startswith("drgn:"):
            return self._exec_drgn(cmd[5:].strip(), timeout, truncate)
        elif cmd.startswith("crash:"):
            return self._exec_crash(cmd[6:].strip(), timeout, truncate)
        elif cmd.startswith("pykdump:"):
            return self._exec_pykdump(cmd[8:].strip(), timeout, truncate)
            
        # Heuristic Routing
        is_drgn = False
        crash_cmds = ['sys', 'bt', 'ps', 'log', 'mount', 'net', 'dev', 'files', 'help', 'set', 'extend']
        first_word = cmd.split()[0] if cmd else ""
        
        if first_word in crash_cmds:
            is_drgn = False
        elif any(x in cmd for x in ['=', '(', '.', '[']):
            is_drgn = True
        elif first_word in ['prog', 'task', 'thread']:
            is_drgn = True
        else:
            is_drgn = False
            
        if is_drgn:
            return self._exec_drgn(cmd, timeout, truncate)
        else:
            return self._exec_crash(cmd, timeout, truncate)

    def execute_with_store(self, command: str, timeout: int = 60, 
                           force: bool = False) -> CommandResult:
        """
        Execute command with caching and persistence.
        
        Args:
            command: Command with optional engine prefix (crash:, drgn:, pykdump:)
            timeout: Command timeout
            force: If True, bypass cache and force re-execution
            
        Returns:
            CommandResult with command_id, output_file, total_lines, etc.
        """
        engine, cmd = self._parse_command(command)
        
        # Get context relevant to this command
        relevant_context = self._get_relevant_context(cmd)
        
        # Check cache (unless forced or disabled)
        cache_mode = Config.COMMAND_CACHE_MODE
        if self.command_store and not force and cache_mode != "disable":
            cached = self.command_store.get_cached(engine, cmd, relevant_context)
            if cached:
                # normal: only use cache for persisted (file-backed) results
                # force: use cache for all results (file + memory)
                if cache_mode == "normal" and not cached.output_file:
                    cached = None  # Skip memory-only cache, re-execute
                if cached:
                    logger.debug(f"Cache hit for {engine}:{cmd}")
                    return cached
        
        # Execute command (no truncation - we'll handle that in the tool layer)
        import time
        start_time = time.time()
        output = self.execute_command(f"{engine}:{cmd}", timeout=timeout, truncate=False)
        duration = time.time() - start_time
        
        # Detect if output is an error (should not be cached)
        is_error = output.strip().startswith("Error:")
        
        # Update context if needed (e.g., 'set pid 1234')
        self._maybe_update_context(engine, cmd)
        
        # Persist and return
        if self.command_store:
            return self.command_store.save(engine, cmd, output, relevant_context, 
                                           is_error=is_error, duration=duration)
        
        # Fallback for sessions without workdir
        return CommandResult(
            command_id=f"{engine}:{cmd}",
            command=cmd,
            engine=engine,
            output_file=None,
            total_lines=len(output.splitlines()),
            timestamp=0,
            cached=False,
        )

    def _parse_command(self, command: str) -> Tuple[str, str]:
        """Parse command into (engine, actual_command)."""
        cmd = command.strip()
        if cmd.startswith("drgn:"):
            return "drgn", cmd[5:].strip()
        elif cmd.startswith("crash:"):
            return "crash", cmd[6:].strip()
        elif cmd.startswith("pykdump:"):
            return "pykdump", cmd[8:].strip()
        
        # Default to crash for unspecified
        return "crash", cmd

    def _get_relevant_context(self, cmd: str) -> Dict[str, str]:
        """Get context relevant to a command (for command_id generation)."""
        cmd_word = cmd.strip().split()[0] if cmd.strip() else ""
        if cmd_word in self.CONTEXT_DEPENDENT_COMMANDS:
            return self.context.copy()
        return {}

    def _maybe_update_context(self, engine: str, cmd: str):
        """Parse 'set pid/cpu' commands to update context."""
        if engine != "crash":
            return
        parts = cmd.strip().split()
        if len(parts) >= 3 and parts[0] == "set":
            key = parts[1]
            value = parts[2]
            if key in self.CONTEXT_KEYS:
                self.context[key] = value
                logger.debug(f"Context updated: {key}={value}")

    def _exec_drgn(self, cmd: str, timeout: int, truncate: bool) -> str:
        if not self.drgn_session or not self.drgn_session.is_active():
            error_msg = self.drgn_start_error
            return f"Error: Drgn engine is not active. (Reason: {error_msg})" if error_msg else "Error: Drgn engine is not active."
        return self.drgn_session.execute_command(cmd, timeout, truncate)

    def _exec_crash(self, cmd: str, timeout: int, truncate: bool) -> str:
        if not self.crash_session or not self.crash_session.is_active():
            error_msg = self.crash_start_error
            return f"Error: Crash engine is not active. (Reason: {error_msg})" if error_msg else "Error: Crash engine is not active."
        return self.crash_session.execute_command(cmd, timeout, truncate)

    def _exec_pykdump(self, code: str, timeout: int, truncate: bool) -> str:
        """Execute pykdump Python code via crash session."""
        if not self.crash_session or not self.crash_session.is_active():
            return "Error: Crash engine is not active."
        return self.crash_session.run_pykdump(code, is_file=False, timeout=timeout, truncate=truncate)

    def close(self):
        if self.crash_session:
            self.crash_session.close()
        if self.drgn_session:
            self.drgn_session.close()
    
    def stop(self):
        """Alias for close() for API compatibility."""
        self.close()
            
    def is_active(self) -> bool:
        return (self.crash_session and self.crash_session.is_active()) or \
               (self.drgn_session and self.drgn_session.is_active())
