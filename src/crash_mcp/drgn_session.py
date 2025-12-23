import pexpect
import logging
import os

logger = logging.getLogger(__name__)

class DrgnSession:
    """
    Manages an interactive session with the 'drgn' utility.
    """
    PROMPT = r'>>> '

    def __init__(self, dump_path: str, kernel_path: str = None, binary_path: str = 'drgn',
                 remote_host: str = None, remote_user: str = None):
        self.dump_path = dump_path
        self.kernel_path = kernel_path
        self.remote_host = remote_host
        self.remote_user = remote_user
        self._process = None
        # Allow overriding binary path via env var for testing (e.g. using mock_drgn.py)
        self.binary_path = os.environ.get('DRGN_BINARY', binary_path)


    def start(self, timeout: int = 30):
        """
        Starts the drgn session.
        """
        # drgn usage: drgn -c <vmcore> -s <vmlinux>
        # or just drgn <vmcore> <vmlinux> depending on version/usage, 
        # but typically explicit flags are safer.
        # However, looking at standard usage: `drgn vmcore vmlinux` works too.
        # Let's use flags for clarity if supported, but simple args are robust.
        # We'll use module execution `python3 -m drgn` if binary_path is python, 
        # but assuming `drgn` command exists or we use the mock.
        
        args = []
        # If we are using the mock, we might be passing just args. 
        # Real drgn: drgn -c core -s vmlinux
        
        if self.dump_path:
             args.extend(['-c', self.dump_path])
        
        if self.kernel_path:
            args.extend(['-s', self.kernel_path])
            
        if self.remote_host:
            # Remote Execution via SSH
            ssh_cmd = ['ssh']
            if self.remote_user:
                ssh_cmd.append(f"{self.remote_user}@{self.remote_host}")
            else:
                ssh_cmd.append(self.remote_host)
            
            ssh_cmd.append('-t')
            
            remote_cmd = f"{self.binary_path} {' '.join(args)}"
            ssh_cmd.append(remote_cmd)
            
            spawn_bin = 'ssh'
            spawn_args = ssh_cmd[1:]
            
            logger.info(f"Starting remote drgn session: {' '.join(ssh_cmd)}")
        else:
            spawn_bin = self.binary_path
            spawn_args = args
            logger.info(f"Starting drgn session: {spawn_bin} {' '.join(spawn_args)}")

        try:
            # encoding='utf-8' is important
            self._process = pexpect.spawn(spawn_bin, spawn_args, encoding='utf-8', timeout=timeout)
            
            # Expect the prompt
            self._process.expect(self.PROMPT)
            
            logger.info("Drgn session started successfully.")
            
        except pexpect.exceptions.ExceptionPexpect as e:
            logger.error(f"Failed to start drgn session: {e}")
            if self._process:
                logger.error(f"Output before failure: {self._process.before}")
            raise RuntimeError(f"Failed to start drgn session: {e}")

    def execute_command(self, command: str, timeout: int = 60, truncate: bool = True) -> str:
        """
        Executes a python command in the drgn session and returns the output.
        """
        if not self._process or not self._process.isalive():
            raise RuntimeError("Drgn session is not active")

        logger.debug(f"Executing drgn command: {command}")
        
        if command.strip() in ['quit()', 'exit()']:
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
            
            # Smart Truncation
            MAX_LEN = 16384 
            
            if len(output) > MAX_LEN:
                removed_chars = len(output) - MAX_LEN
                logger.warning(f"Output truncated. Original length: {len(output)}. Removed {removed_chars} chars.")
                
                HEAD_LEN = 4096
                TAIL_LEN = MAX_LEN - HEAD_LEN
                
                output = (
                    output[:HEAD_LEN] + 
                    f"\n\n... [Output truncated by Drgn MCP ({removed_chars} characters skipped)] ...\n\n" + 
                    output[-TAIL_LEN:]
                )
            
            return output

        except pexpect.TIMEOUT:
            logger.error(f"Command '{command}' timed out")
            raise TimeoutError(f"Command '{command}' timed out")
        except pexpect.EOF:
            logger.error("Drgn session ended unexpectedly")
            self._process = None
            raise RuntimeError("Drgn session ended unexpectedly")

    def close(self):
        """
        Terminates the drgn session.
        """
        if self._process and self._process.isalive():
            logger.info("Closing drgn session...")
            try:
                self._process.sendline('quit()')
                self._process.close()
            except Exception as e:
                logger.warning(f"Error closing session gracefully: {e}")
                self._process.terminate(force=True)
            self._process = None

    def is_active(self) -> bool:
        return self._process is not None and self._process.isalive()
