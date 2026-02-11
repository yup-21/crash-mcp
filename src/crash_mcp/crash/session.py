import logging
import os
from pathlib import Path
from typing import Optional, List, Tuple
from crash_mcp.common.base_session import BaseSession
from crash_mcp.config import Config

logger = logging.getLogger(__name__)

class CrashSession(BaseSession):
    """
    Manages an interactive session with the 'crash' utility.
    Supports automatic architecture detection and crash binary selection.
    """
    # Prompt pattern matches: "crash> ", "crash-arm64> ", etc.
    PROMPT = r'crash[-\w]*> '

    def __init__(self, dump_path: str, kernel_path: Optional[str] = None, binary_path: str = None,
                 remote_host: Optional[str] = None, remote_user: Optional[str] = None, ssh_key: Optional[str] = None,
                 crash_args: List[str] = None, auto_detect_arch: bool = True):
        """
        Initialize CrashSession.
        
        Args:
            dump_path: Path to vmcore dump file
            kernel_path: Path to vmlinux with debug symbols
            binary_path: Path to crash binary. If None and auto_detect_arch=True,
                        will auto-select based on vmcore architecture.
            remote_host: Remote host for SSH connection
            remote_user: SSH username
            ssh_key: Optional SSH key path
            crash_args: Extra crash arguments
            auto_detect_arch: If True, auto-detect vmcore architecture and select
                             appropriate crash binary (Local only)
        """
        
        final_binary_path = binary_path
        self.detected_arch = None
        
        # Auto-detect architecture and select crash binary if needed
        # Only auto-detect for local sessions if binary not provided
        if not final_binary_path and auto_detect_arch and not remote_host:
             final_binary_path, self.detected_arch = self._auto_select_binary(dump_path, kernel_path)
        
        if not final_binary_path:
            final_binary_path = 'crash'
            
        super().__init__(dump_path, kernel_path, final_binary_path, remote_host, remote_user, ssh_key)
        
        self.crash_args = crash_args or []

    def _auto_select_binary(self, dump_path, kernel_path) -> Tuple[str, Optional[str]]:
        """Auto-select crash binary based on vmcore architecture."""
        try:
            from crash_mcp.common.arch_detect import find_crash_binary
            
            binary_path, detected_arch = find_crash_binary(
                vmcore_path=dump_path,
                vmlinux_path=kernel_path
            )
            logger.info(f"Auto-selected crash binary: {binary_path} for {detected_arch}")
            return binary_path, detected_arch
        except ImportError:
            logger.warning("Auto-detection module not found. Using default 'crash'.")
            return 'crash', None
        except FileNotFoundError as e:
            logger.warning(f"Auto-detection failed: {e}")
            logger.info("Falling back to generic 'crash' binary")
            return 'crash', None
            
    def construct_args(self) -> List[str]:
        """Construct arguments for crash binary."""
        args = []
        # Add -x flag to auto-load extensions from CRASH_EXTENSIONS
        if Config.CRASH_EXTENSION_LOAD:
            args.append("-x")
        # Add -s to suppress startup banner/copyright for cleaner parsing
        args.append("-s")
        # Add custom crash args
        args.extend(self.crash_args)
        if self.kernel_path:
            args.append(self.kernel_path)
        args.append(self.dump_path)
        return args

    def _post_start_init(self):
        """
        Handle post-start initialization (wait for prompt, configure session).
        """
        # Expect the initial prompt
        logger.debug(f"Waiting for prompt: {self.PROMPT}")
        try:
            self._process.expect(self.PROMPT, timeout=10)
            logger.debug("Initial prompt matched.")
        except pexpect.TIMEOUT:
            logger.error(f"Timeout waiting for startup prompt. Output found so far: {repr(self._process.before)}")
            raise
        except pexpect.EOF:
            logger.error(f"EOF waiting for startup prompt. Output found so far: {repr(self._process.before)}")
            raise
        
        # Disable scrolling/paging to avoid hanging on long output
        self._process.sendline('set scroll off')
        self._process.expect(self.PROMPT)

        # Disable Debuginfod to prevent GDB from hanging on network requests
        self._process.sendline('gdb set debuginfod enabled off')
        self._process.expect(self.PROMPT)


    def get_default_context(self) -> dict:
        """
        Query crash's current context (pid, cpu) for cache consistency.
        
        Returns:
            Dict with 'pid' and/or 'cpu' keys if available.
        """
        import re
        context = {}
        
        try:
            # Run 'set' command to get current settings
            output = self.execute_command('set', timeout=10, truncate=False)
            
            # Parse pid: looks like "      pid: 1234"
            pid_match = re.search(r'^\s*pid:\s*(\d+)', output, re.MULTILINE)
            if pid_match:
                context['pid'] = pid_match.group(1)
                logger.debug(f"Crash default pid: {context['pid']}")
            
            # Parse cpu: looks like "      cpu: 0" or "      cpu: -1" (any)
            cpu_match = re.search(r'^\s*cpu:\s*(-?\d+)', output, re.MULTILINE)
            if cpu_match:
                cpu_val = cpu_match.group(1)
                # Only track if specific CPU is set (not -1 which means "any")
                if cpu_val != '-1':
                    context['cpu'] = cpu_val
                    logger.debug(f"Crash default cpu: {context['cpu']}")
                    
        except Exception as e:
            logger.warning(f"Failed to get crash default context: {e}")
        
        return context

    def run_pykdump(self, script_or_code: str, is_file: bool = False, 
                   timeout: int = 60, truncate: bool = True) -> str:
        """
        Execute pykdump Python code or script file.
        
        Args:
            script_or_code: Python code string or path to .py script file
            is_file: If True, treat script_or_code as a file path
            timeout: Command timeout in seconds
            truncate: Whether to truncate long output
            
        Returns:
            Command output string
        """
        
        if is_file:
            # Execute script file directly
            cmd = f"epython {script_or_code}"
        else:
            # Fix potential double-escaped newlines from LLM
            script_or_code = script_or_code.replace('\\n', '\n')
            
            # epython in mpykdump may not support -c, so we write to a temp file
            import tempfile
            import os
            
            # Create a temp file in the current working directory or /tmp
            # We prefer CWD so crash can see it easily if there are path issues,
            # but /tmp is cleaner. Let's try to write to a known temp location accessible by crash.
            # Since we are running crash essentially locally, /tmp is fine.
            # Note: We need to ensure the file persists until executed.
            
            # We'll create a file with a unique name
            fd, path = tempfile.mkstemp(suffix=".py", text=True)
            with os.fdopen(fd, 'w') as f:
                f.write(script_or_code)
            
            # We must remember to clean this up, but execute_command is synchronous.
            # However, prompt return does not guarantee command finished if we backgrounded it,
            # but here we wait for prompt.
            
            cmd = f"epython {path}"
            
            # We can try to append a cleanup command? No, crash shell doesn't do chaining easily like shell.
            # We will just execute it. The file will remain in /tmp.
            # For a long running service this is bad, but for a session it is acceptable
            # or we can try to delete it after.
            
        try:
             result = self.execute_command(cmd, timeout=timeout, truncate=truncate)
        finally:
             if not is_file and 'path' in locals() and os.path.exists(path):
                 try:
                    os.unlink(path)
                 except OSError:
                    pass

        return result

    def _smart_truncate(self, output: str, command: str) -> str:
        """
        Override smart truncation to handle specific commands like 'log'.
        """
        # Default limit: 16KB
        MAX_LEN = 16384
        
        if len(output) <= MAX_LEN:
            return output
            
        # Command-Aware Strategies
        clean_cmd = command.strip().split()[0]
        
        if clean_cmd == 'log':
            removed_chars = len(output) - MAX_LEN
            logger.warning(f"Output truncated (log tail). Original length: {len(output)}. Removed {removed_chars} chars.")
            # Tail-Only Strategy for log: Keep last MAX_LEN
            return (
                f"... [Log truncated (Head). Showing last {MAX_LEN} chars] ...\n\n" + 
                output[-MAX_LEN:]
            )
        
        # Delegate to default strategy for other commands
        return super()._smart_truncate(output, command)
