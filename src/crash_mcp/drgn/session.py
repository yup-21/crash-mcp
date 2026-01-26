import logging
import os
from typing import List, Optional
from crash_mcp.common.base_session import BaseSession

logger = logging.getLogger(__name__)

class DrgnSession(BaseSession):
    PROMPT = r'>>> '

    def __init__(self, dump_path: str, kernel_path: Optional[str] = None, binary_path: str = 'drgn', tools_path: str = "", **kwargs):
        super().__init__(dump_path, kernel_path, binary_path, **kwargs)
        self.tools_path = tools_path
        
        # [Ported Feature] Automatic Path Resolution from previous work
        # If binary is just 'drgn', try to find it in the same directory as python executable
        if self.binary_path == 'drgn':
            import sys
            candidate = os.path.join(os.path.dirname(sys.executable), 'drgn')
            if os.path.exists(candidate):
                logger.info(f"Resolved drgn binary path to: {candidate}")
                self.binary_path = candidate

    def construct_args(self) -> List[str]:
        # Drgn usage: drgn -c vmcore -s vmlinux
        args = []
        if self.dump_path:
            args.extend(['-q', '-c', self.dump_path]) # Added -q for quiet startup
        if self.kernel_path:
            args.extend(['-s', self.kernel_path])
        return args
    
    def _sync(self):
        """Force a synchronization of the session."""
        # We use a calculation so the result (output) is different from the command (echo).
        # Command: print(11111 * 11111)
        # Echo: print(11111 * 11111)
        # Output: 123454321
        magic_val = 12345679
        magic_multiplier = 9
        expected_result = str(magic_val * magic_multiplier) # 111111111
        
        self._process.sendline(f"print({magic_val} * {magic_multiplier})")
        
        # We must see the EXPECTED RESULT. The echo will contain the expression, not the result.
        self._process.expect(expected_result)
        
        # Then we expect the prompt.
        self._process.expect(self.PROMPT)
        
    from typing import Callable

    def start(self, timeout=120, on_progress: Optional[Callable[[float, str], None]] = None):
        super().start(timeout, on_progress)
        # 1. Initial sync to clear startup noise (imports, etc)
        self._sync()
        
        # 2. Inject tools path if needed
        # We do this AFTER we are sure the session is synchronized.
        if self.tools_path:
            logger.info(f"Adding drgn-tools path: {self.tools_path}")
            safe_path = self.tools_path.replace("'", "\\'")
            
            # Use Secure Injection Pattern:
            # Append a print statement to ensure we can verify execution completion
            # independent of prompts on the echo.
            token = "INJECT_DONE"
            cmd = f"import sys; sys.path.append('{safe_path}'); print('{token}')"
            
            self._process.sendline(cmd)
            # Expect the output token (proving execution finished)
            self._process.expect(token)
            # Then expect the prompt
            self._process.expect(self.PROMPT)
            
            # 3. Final Sync to ensure buffer clear
            self._sync()
        
    def execute_command(self, command: str, timeout: int = 60, truncate: bool = True) -> str:
        # Override to handle Python REPL echo (>>> and ... prompts) and multi-line
        if not self.is_active():
            raise RuntimeError("Drgn session is not active")
            
        # [Ported Feature] Automatically use run_script for multi-line commands
        # [Ported Feature] Automatically use run_script for multi-line commands
        stripped_cmd = command.strip()
        
        # 1. Check if it's a file path (ends with .py)
        if stripped_cmd.endswith('.py') and not '\n' in stripped_cmd:
            script_path = stripped_cmd
            # Support absolute path or relative to CWD
            if os.path.exists(script_path):
                try:
                    with open(script_path, 'r') as f:
                        script_content = f.read()
                    logger.info(f"Executing drgn script from file: {script_path}")
                    return self.run_script(script_content)
                except Exception as e:
                    return f"Error reading script file {script_path}: {e}"
            else:
                return f"Error: Script not found: {script_path}"

        # 2. Multi-line command -> run_script (base64)
        if '\n' in stripped_cmd:
            return self.run_script(stripped_cmd)
            
        self._process.sendline(command)
        self._process.expect(self.PROMPT, timeout=timeout)
        raw_output = self._process.before
        
        # Smart Echo Stripping
        # The REPL echoes input lines. Continuation lines are prefixed with "... "
        # We want to remove all lines that correspond to the input command.
        
        input_lines = command.strip().splitlines()
        output_lines = raw_output.splitlines()
        
        cleaned_output = []
        input_idx = 0
        
        # We iterate through output lines and try to match them with input lines
        
        # We only strip from the *beginning* of the output.
        stripping = True
        
        import re
        ansi_escape = re.compile(r'\x1b\[[0-9;?]*[a-zA-Z]')
        
        for line in output_lines:
            if not stripping:
                cleaned_output.append(line)
                continue
                
            if input_idx >= len(input_lines):
                # Exhausted input, rest is output
                if line.strip() == "":
                    continue # Skip empty line separator
                else:
                    stripping = False
                    cleaned_output.append(line)
                continue
            
            target = input_lines[input_idx].strip()
            current = line.strip()
            
            # Remove prompt prefixes
            if current.startswith(">>> "):
                current = current[4:]
            elif current.startswith("... "):
                current = current[4:]
            
            # Clean ANSI
            current = ansi_escape.sub('', current)
                
            if current == target:
                input_idx += 1
            else:
                # Mismatch. 
                if current in ["...", ">>>"]:
                     continue
                
                stripping = False
                cleaned_output.append(line)
                
        result = "\n".join(cleaned_output).strip()
        
        if truncate:
            return self._smart_truncate(result, command)
        return result

    def run_script(self, script: str) -> str:
        """
        Executes a script safely by wrapping it in base64/exec.
        This prevents early prompt matching on multi-statement scripts
        and handles output interleaving correctly.
        """
        import base64
        encoded = base64.b64encode(script.encode('utf-8')).decode('utf-8')
        
        # We construct a single-line command
        wrapper = f"import base64; exec(base64.b64decode('{encoded}'))"
        
        # execute_command (single line) will handle it
        # We force truncate=False because script output might be large?
        # Or let execute_command handle truncation? BaseSession handles it.
        # But here we call self.execute_command which overrides and calls self._smart_truncate
        return self.execute_command(wrapper, truncate=False)
