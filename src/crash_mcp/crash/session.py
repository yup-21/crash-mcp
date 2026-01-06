import logging
from typing import Optional, List, Tuple
from crash_mcp.common.session import BaseSession

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
            from crash_mcp.arch_detect import find_crash_binary
            
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
        # Add custom crash args first
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
        self._process.expect(self.PROMPT)
        
        # Disable scrolling/paging to avoid hanging on long output
        self._process.sendline('set scroll off')
        self._process.expect(self.PROMPT)
        
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
