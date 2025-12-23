import pexpect
import logging
import re

logger = logging.getLogger(__name__)

class CrashSession:
    """
    Manages an interactive session with the 'crash' utility.
    """
    PROMPT = r'crash> '

    def __init__(self, dump_path: str, kernel_path: str = None, binary_path: str = 'crash',
                 remote_host: str = None, remote_user: str = None):
        self.dump_path = dump_path
        self.kernel_path = kernel_path
        self.binary_path = binary_path
        self.remote_host = remote_host
        self.remote_user = remote_user
        self._process = None


    def start(self, timeout: int = 30):
        """
        Starts the crash session.
        """
        args = []
        if self.kernel_path:
            args.append(self.kernel_path)
        args.append(self.dump_path)

        if self.remote_host:
            # Remote Execution via SSH
            # ssh user@host -t "crash args"
            ssh_cmd = ['ssh']
            if self.remote_user:
                ssh_cmd.append(f"{self.remote_user}@{self.remote_host}")
            else:
                ssh_cmd.append(self.remote_host)
            
            # Force pseudo-terminal allocation for interactive session
            ssh_cmd.append('-t')
            
            # Join local args for the remote command string
            # naive joining; strictly we should quote args if they have spaces
            remote_cmd = f"{self.binary_path} {' '.join(args)}"
            ssh_cmd.append(remote_cmd)
            
            spawn_bin = 'ssh'
            spawn_args = ssh_cmd[1:]
            
            logger.info(f"Starting remote crash session: {' '.join(ssh_cmd)}")
        else:
            # Local Execution
            spawn_bin = self.binary_path
            spawn_args = args
            logger.info(f"Starting crash session: {self.binary_path} {' '.join(args)}")

        try:
            # encoding='utf-8' is important for pexpect in Python 3
            self._process = pexpect.spawn(spawn_bin, spawn_args, encoding='utf-8', timeout=timeout)
            
            # Wait for the initial prompt to ensure session is ready
            # We might need to handle cases where it asks for terminal type or page size, 
            # though usually 'crash' is well behaved if TERM is set or arguments are passed.
            # Using -s (silent) or --minimal might be good options if supported, 
            # but standard invocation is safer for compatibility.
            
            # Expect the prompt
            self._process.expect(self.PROMPT)
            
            # Disable scrolling/paging to avoid hanging on long output
            self._process.sendline('set scroll off')
            self._process.expect(self.PROMPT)
            
            logger.info("Crash session started successfully.")
            
        except pexpect.exceptions.ExceptionPexpect as e:
            logger.error(f"Failed to start crash session: {e}")
            if self._process:
                logger.error(f"Output before failure: {self._process.before}")
            raise RuntimeError(f"Failed to start crash session: {e}")

    def execute_command(self, command: str, timeout: int = 60, truncate: bool = True) -> str:
        """
        Executes a command in the crash session and returns the output.
        """
        if not self._process or not self._process.isalive():
            raise RuntimeError("Crash session is not active")

        logger.debug(f"Executing command: {command}")
        
        # specific handling for quit/exit to avoid hanging
        if command.strip() in ['q', 'quit', 'exit']:
            self.close()
            return "Session closed"

        try:
            # Send the command
            self._process.sendline(command)
            
            # Wait for prompt
            self._process.expect(self.PROMPT, timeout=timeout)
            
            # content before the prompt is the command output (plus the command echo)
            raw_output = self._process.before
            
            # Clean up the output
            # 1. Remove the command echo (first line usually)
            lines = raw_output.splitlines()
            if lines and command.strip() in lines[0]:
                lines = lines[1:]
            
            output = "\n".join(lines).strip()
            
            if not truncate:
                return output
            
            # Smart Truncation: Prevent token overflow
            # Default limit: 16KB (approx 4k tokens, safe buffer)
            MAX_LEN = 16384 
            
            if len(output) > MAX_LEN:
                removed_chars = len(output) - MAX_LEN
                logger.warning(f"Output truncated. Original length: {len(output)}. Removed {removed_chars} chars.")
                
                # Command-Aware Strategies
                clean_cmd = command.strip().split()[0]
                
                if clean_cmd == 'log':
                    # Tail-Only Strategy for log: Keep last MAX_LEN
                    output = (
                        f"... [Log truncated (Head). Showing last {MAX_LEN} chars] ...\n\n" + 
                        output[-MAX_LEN:]
                    )
                else:
                    # Default Head+Tail Strategy
                    # Adjusted ratio: 4KB Head (Context) + 12KB Tail (Recent info)
                    HEAD_LEN = 4096
                    TAIL_LEN = MAX_LEN - HEAD_LEN # 12288
                    
                    output = (
                        output[:HEAD_LEN] + 
                        f"\n\n... [Output truncated by Crash MCP ({removed_chars} characters skipped). Use specific commands to view more.] ...\n\n" + 
                        output[-TAIL_LEN:]
                    )
            
            return output

        except pexpect.TIMEOUT:
            logger.error(f"Command '{command}' timed out")
            raise TimeoutError(f"Command '{command}' timed out")
        except pexpect.EOF:
            logger.error("Crash session ended unexpectedly")
            self._process = None
            raise RuntimeError("Crash session ended unexpectedly")

    def close(self):
        """
        Terminates the crash session.
        """
        if self._process and self._process.isalive():
            logger.info("Closing crash session...")
            try:
                self._process.sendline('quit')
                self._process.close()
            except Exception as e:
                logger.warning(f"Error closing session gracefully: {e}")
                self._process.terminate(force=True)
            self._process = None

    def is_active(self) -> bool:
        return self._process is not None and self._process.isalive()
