import pexpect
import logging
import os
import re
import uuid
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# ANSI escape sequence pattern - matches all common terminal control sequences
# Includes: colors (SGR), cursor movement, screen clearing, bracketed paste mode, etc.
# Pattern breakdown:
#   \x1b\[[0-9;?]*[a-zA-Z]  - CSI sequences (includes DEC private modes like ?2004l)
#   \x1b\].*?\x07           - OSC sequences (window titles, etc.)
ANSI_ESCAPE_PATTERN = re.compile(r'\x1b\[[0-9;?]*[a-zA-Z]|\x1b\].*?\x07')

class BaseSession:
    """
    Abstract base class for interactive debugger sessions.
    """
    PROMPT = None  # Must be defined by subclasses

    CONFIG_OPTS_PATTERN = None # To be defined by subclasses if needed
    
    def __init__(self, dump_path: str, kernel_path: Optional[str] = None, binary_path: str = None, 
                 remote_host: Optional[str] = None, remote_user: Optional[str] = None, ssh_key: Optional[str] = None):
        self.dump_path = dump_path
        self.kernel_path = kernel_path
        self.binary_path = binary_path
        
        # Remote Debugging Config
        self.remote_host = remote_host
        self.remote_user = remote_user
        self.ssh_key = ssh_key
        
        self.session_id = str(uuid.uuid4())
        self._process = None
        self.history = []

    def construct_args(self) -> List[str]:
        """
        Constructs command-line arguments for the binary.
        Must be implemented by subclasses.
        """
        raise NotImplementedError

    from typing import Callable

    def start(self, timeout: int = 30, on_progress: Optional[Callable[[float, str], None]] = None):
        """
        Starts the interactive session.
        """
        if not self.binary_path:
            raise ValueError("Binary path not specified")

        # 1. Validate Environment
        if on_progress: on_progress(0, "Validating environment")
        if self.remote_host:
            self.validate_remote_environment()
        else:
            self.validate_local_environment()

        # 2. Construct local base command
        args = self.construct_args()
        cmd_str = f"{self.binary_path} {' '.join(args)}"
        
        try:
            # 3. Wrap via SSH if remote
            if self.remote_host:
                logger.info(f"Configuring remote session to {self.remote_host}")
                
                # SSH Command Construction
                # ssh [-i key] [user@]host "command"
                # Note: We need -tt to force pseudo-tty allocation for interactive session
                ssh_binary = "ssh"
                ssh_args = ["-tt", "-o", "StrictHostKeyChecking=no"] # -tt is critical for pexpect interaction
                
                if self.ssh_key:
                    ssh_args.extend(["-i", self.ssh_key])
                
                target = f"{self.remote_user}@{self.remote_host}" if self.remote_user else self.remote_host
                ssh_args.append(target)
                
                # Append the actual command as a single argument string
                ssh_args.append(cmd_str)
                
                logger.info(f"Starting REMOTE session: {ssh_binary} {' '.join(ssh_args)}")
                
                # For pexpect spawn: binary is ssh, args is list of ssh flags + command
                # maxread=65536 增大缓冲区以处理长输出 (help, log 等)
                self._process = pexpect.spawn(ssh_binary, ssh_args, encoding='utf-8', timeout=timeout, maxread=65536)
            else:
                logger.info(f"Starting LOCAL session: {cmd_str}")
                
                # Build environment with CRASH_EXTENSIONS for extension search paths
                env = os.environ.copy()
                from crash_mcp.config import get_extension_paths
                
                ext_paths = get_extension_paths()
                
                if env.get("CRASH_EXTENSIONS"):
                    ext_paths.append(env["CRASH_EXTENSIONS"])
                
                if ext_paths:
                    env["CRASH_EXTENSIONS"] = ":".join(ext_paths)
                    logger.debug(f"CRASH_EXTENSIONS: {env['CRASH_EXTENSIONS']}")
                
                logger.debug(f"Calling spawn for {self.binary_path}...")
                
                # [Fix for Hang] Use PopenSpawn + script wrapper to avoid pty.fork() threading deadlocks
                # and ensure TTY behavior (line buffering) for interactive tools like prompt.
                try:
                    from pexpect.popen_spawn import PopenSpawn
                    import shlex
                    
                    # Construct command string for script
                    real_cmd_list = [self.binary_path] + args
                    real_cmd_str = shlex.join(real_cmd_list)
                    
                    # script -q -c "cmd..." /dev/null
                    # Note: script parameters can vary by platform, but -q -c is standard on Linux
                    wrapper_cmd = ["script", "-q", "-c", real_cmd_str, "/dev/null"]
                    
                    logger.info(f"Spawning via PopenSpawn with script wrapper: {wrapper_cmd}")
                    self._process = PopenSpawn(wrapper_cmd, encoding='utf-8', timeout=timeout, env=env)
                    
                except ImportError:
                    logger.warning("PopenSpawn not found, falling back to pexpect.spawn (unsafe in threaded env)")
                    # Remove maxread=65536 which might be causing issues in this environment
                    self._process = pexpect.spawn(self.binary_path, args, encoding='utf-8', timeout=timeout, env=env)
                    
                logger.debug(f"Process spawned. PID: {self._process.pid}")
            
            # Post-start initialization (wait for prompt, set options)
            logger.debug("Calling _post_start_init()...")
            self._post_start_init()
            logger.debug("_post_start_init() completed.")
            
            logger.info(f"{self.__class__.__name__} started successfully.")
            
        except pexpect.exceptions.ExceptionPexpect as e:
            logger.error(f"Failed to start session: {e}")
            if self._process:
                logger.error(f"Output before failure: {self._process.before}")
            raise RuntimeError(f"Failed to start session: {e}")

    def _post_start_init(self):
        """
        Hook for post-start initialization (e.g., waiting for prompt).
        Can be overridden by subclasses.
        """
        if self.PROMPT:
            self._process.expect(self.PROMPT)

    def execute_command(self, command: str, timeout: int = 60, truncate: bool = True) -> str:
        """
        Executes a command in the session and returns the output.
        """
        if not self.is_active():
            raise RuntimeError("Session is not active")

        logger.debug(f"Executing command: {command}")
        
        # specific handling for quit/exit to avoid hanging
        if command.strip() in ['q', 'quit', 'exit']:
            self.close()
            return "Session closed"

        try:
            # 清空可能的残留缓冲区
            # 使用非阻塞读取尝试清空
            try:
                while True:
                    # 尝试读取任何残留数据，超时 0.1 秒
                    self._process.expect(self.PROMPT, timeout=0.1)
            except pexpect.TIMEOUT:
                # 没有更多数据，正常
                pass
            except pexpect.EOF:
                raise RuntimeError("Session unexpectedly closed")
            
            # Send the command
            self._process.sendline(command)
            
            # Wait for prompt - 使用循环确保读取完整输出
            output_parts = []
            while True:
                try:
                    index = self._process.expect([self.PROMPT, pexpect.TIMEOUT], timeout=timeout)
                    output_parts.append(self._process.before)
                    
                    if index == 0:
                        # 匹配到 prompt，命令完成
                        break
                    else:
                        # 超时但继续尝试 (可能输出太长)
                        logger.warning(f"Command output taking longer than expected")
                        break
                except pexpect.EOF:
                    output_parts.append(self._process.before)
                    raise RuntimeError("Session closed unexpectedly")
            
            raw_output = "".join(output_parts)
            
            # Clean up the output
            # 1. Remove the command echo (first line usually)
            lines = raw_output.splitlines()
            if lines and command.strip() in lines[0]:
                lines = lines[1:]
            
            output = "\n".join(lines).strip()
            
            # Strip ANSI escape sequences (color codes like \x1b[36m)
            output = ANSI_ESCAPE_PATTERN.sub('', output)
            
            # [Session History] Track History
            import time
            entry = {
                "timestamp": time.time(),
                "command": command,
                "output_len": len(output),
                "output_summary": output[:200] + "..." if len(output) > 200 else output
            }
            if not hasattr(self, 'history'): self.history = []
            self.history.append(entry)
            
            if not truncate:
                return output
            
            return self._smart_truncate(output, command)

        except pexpect.TIMEOUT:
            logger.error(f"Command '{command}' timed out")
            raise TimeoutError(f"Command '{command}' timed out")
        except pexpect.EOF:
            logger.error("Session ended unexpectedly")
            self._process = None
            raise RuntimeError("Session ended unexpectedly")

    def _smart_truncate(self, output: str, command: str) -> str:
        """
        Applies smart truncation to the output.
        Can be overridden or enhanced by subclasses for specific command logic.
        """
        # Default limit: 16KB (approx 4k tokens, safe buffer)
        MAX_LEN = 16384 
        
        if len(output) <= MAX_LEN:
            return output
            
        removed_chars = len(output) - MAX_LEN
        logger.warning(f"Output truncated. Original length: {len(output)}. Removed {removed_chars} chars.")
        
        # Default Head+Tail Strategy
        HEAD_LEN = 4096
        TAIL_LEN = MAX_LEN - HEAD_LEN # 12288
        
        return (
            output[:HEAD_LEN] + 
            f"\\n\\n... [Output truncated by Crash MCP ({removed_chars} characters skipped). Use specific commands to view more.] ...\\n\\n" + 
            output[-TAIL_LEN:]
        )

    def close(self):
        """
        Terminates the session.
        """
        if self.is_active():
            logger.info("Closing session...")
            try:
                self._process.sendline('quit')
                if hasattr(self._process, 'close'):
                    self._process.close()
                elif hasattr(self._process, 'wait'):
                    self._process.wait()
            except Exception as e:
                logger.warning(f"Error closing session gracefully: {e}")
                if hasattr(self._process, 'terminate'):
                    self._process.terminate(force=True)
                elif hasattr(self._process, 'kill'):
                     try:
                        import signal
                        self._process.kill(signal.SIGKILL)
                     except:
                        pass
            self._process = None

    def validate_remote_environment(self):
        """
        Checks if the remote host has the necessary tools and determines architecture.
        """
        import subprocess
        
        logger.info(f"Validating remote environment on {self.remote_host}...")
        
        # Build check command: uname -m && which crash
        # We also check for python3 as Drgn needs it?
        # Note: binary_path might be 'crash' or 'drgn'. We should check THAT binary.
        binary_name = self.binary_path.split('/')[-1] # simple check
        
        check_cmd = f"uname -m && which {binary_name}"
        
        ssh_binary = "ssh"
        ssh_args = ["-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=5"]
        if self.ssh_key:
            ssh_args.extend(["-i", self.ssh_key])
            
        target = f"{self.remote_user}@{self.remote_host}" if self.remote_user else self.remote_host
        ssh_args.append(target)
        ssh_args.append(check_cmd)
        
        try:
            logger.debug(f"Running validation check: {ssh_binary} {ssh_args}")
            # Run with subprocess to capture output without pexpect complexity
            result = subprocess.run([ssh_binary] + ssh_args, capture_output=True, text=True, timeout=10)
            
            if result.returncode != 0:
                error_msg = f"Remote validation failed (Exit {result.returncode}).\\nStderr: {result.stderr.strip()}"
                logger.error(error_msg)
                raise RuntimeError(f"Remote host {self.remote_host} does not have required tools or is unreachable.\\n{error_msg}")
                
            output_lines = result.stdout.strip().splitlines()
            if output_lines:
                arch = output_lines[0].strip()
                tool_path = output_lines[1].strip() if len(output_lines) > 1 else "Unknown"
                logger.info(f"Remote Architecture: {arch}")
                logger.info(f"Remote Tool Path: {tool_path}")
                
                # We could set self.arch here if we want to store it
                self.arch = arch
                
        except subprocess.TimeoutExpired:
            raise TimeoutError(f"Connection to {self.remote_host} timed out during validation.")
        except Exception as e:
            raise RuntimeError(f"Remote validation error: {e}")

    def validate_local_environment(self):
        """
        Validates local tools and detects architecture.
        """
        import platform
        import shutil
        import os
        
        # 1. Check Architecture
        self.arch = platform.machine()
        logger.info(f"Local Architecture: {self.arch}")
        
        # 2. Check Binary
        binary_name = self.binary_path.split('/')[-1]
        
        # Check if binary exists (using shutil.which or os.access)
        if "/" in self.binary_path:
             if not os.path.exists(self.binary_path) or not os.access(self.binary_path, os.X_OK):
                 raise RuntimeError(f"Binary '{self.binary_path}' not found or not executable locally.")
        else:
             if not shutil.which(self.binary_path):
                 raise RuntimeError(f"Binary '{self.binary_path}' not found in PATH.")
             
        logger.info(f"Local tool '{binary_name}' check passed.")

    def is_active(self) -> bool:
        if self._process is None:
            return False
        # Request compat: PopenSpawn vs pexpect.spawn
        if hasattr(self._process, 'isalive'):
            return self._process.isalive()
        # PopenSpawn has .proc which is a subprocess.Popen object
        if hasattr(self._process, 'proc'):
            return self._process.proc.poll() is None
        return False
