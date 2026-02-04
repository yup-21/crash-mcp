"""Command output persistence and retrieval."""
import re
import time
import hashlib
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class CommandResult:
    """Single command execution result."""
    command_id: str           # e.g., "crash:bt@pid=1234"
    command: str
    engine: str
    output_file: Path
    total_lines: int
    timestamp: float
    cached: bool = False
    is_error: bool = False    # True if output indicates an error


class CommandStore:
    """Persists command outputs and provides pagination/search."""
    
    def __init__(self, workdir: Path):
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        self._commands: Dict[str, CommandResult] = {}  # command_id -> result
        self._index = 0
        logger.debug(f"CommandStore initialized at {self.workdir}")
    
    def save(self, engine: str, command: str, output: str, 
             context: Dict[str, str], is_error: bool = False) -> CommandResult:
        """Persist command output to file, return result."""
        command_id = self._make_id(engine, command, context)
        
        # Check if already exists (update timestamp)
        if command_id in self._commands:
            existing = self._commands[command_id]
            try:
                existing.output_file.write_text(output)
            except IOError as e:
                logger.error(f"Failed to write output file: {e}")
                raise
            existing.total_lines = len(output.splitlines())
            existing.timestamp = time.time()
            existing.cached = False
            existing.is_error = is_error
            return existing
        
        # Unique filename
        self._index += 1
        cmd_sanitized = self._sanitize(command.strip().split()[0] if command.strip() else "cmd")
        filename = f"{self._index:04d}_{engine}_{cmd_sanitized}.txt"
        output_file = self.workdir / filename
        try:
            output_file.write_text(output)
        except IOError as e:
            logger.error(f"Failed to write output file: {e}")
            raise
        
        lines = output.splitlines()
        result = CommandResult(
            command_id=command_id,
            command=command,
            engine=engine,
            output_file=output_file,
            total_lines=len(lines),
            timestamp=time.time(),
            cached=False,
            is_error=is_error,
        )
        self._commands[command_id] = result
        logger.debug(f"Saved command output: {command_id} -> {output_file}")
        return result
    
    def get_cached(self, engine: str, command: str, 
                   context: Dict[str, str]) -> Optional[CommandResult]:
        """Check if command exists in cache (same context). Skips error results."""
        command_id = self._make_id(engine, command, context)
        result = self._commands.get(command_id)
        if result and not result.is_error:
            result.cached = True
            logger.debug(f"Cache hit: {command_id}")
            return result
        return None
    
    def get_result(self, command_id: str) -> Optional[CommandResult]:
        """Get command result by ID."""
        return self._commands.get(command_id)
    
    def get_lines(self, command_id: str, offset: int, limit: int) -> Tuple[str, int, int, bool]:
        """Read lines [offset:offset+limit]. 
        
        Returns: (text, returned_count, total_lines, has_more)
        """
        result = self._commands.get(command_id)
        if not result:
            raise ValueError(f"Command not found: {command_id}")
        
        try:
            lines = result.output_file.read_text().splitlines()
        except IOError as e:
            logger.error(f"Failed to read output file: {e}")
            raise ValueError(f"Failed to read output: {e}")
        
        total = len(lines)
        selected = lines[offset:offset + limit]
        has_more = offset + limit < total
        return "\n".join(selected), len(selected), total, has_more
    
    def search(self, command_id: str, query: str, 
               context_lines: int = 3) -> List[Dict]:
        """Search output with regex, return matches with context."""
        result = self._commands.get(command_id)
        if not result:
            raise ValueError(f"Command not found: {command_id}")
        
        try:
            lines = result.output_file.read_text().splitlines()
        except IOError as e:
            logger.error(f"Failed to read output file: {e}")
            raise ValueError(f"Failed to read output: {e}")
        
        try:
            pattern = re.compile(query, re.IGNORECASE)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern: {e}")
        
        matches = []
        for i, line in enumerate(lines):
            if pattern.search(line):
                matches.append({
                    "line_number": i + 1,
                    "context_before": lines[max(0, i-context_lines):i],
                    "line": line,
                    "context_after": lines[i+1:i+1+context_lines],
                })
        
        logger.debug(f"Search '{query}' in {command_id}: {len(matches)} matches")
        return matches
    
    def _make_id(self, engine: str, command: str, context: Dict[str, str]) -> str:
        """Generate unique command_id using hash.
        
        Format: "engine:cmd_prefix:hash[:context_hash]"
        """
        cmd = command.strip()
        cmd_prefix = cmd.split()[0][:10] if cmd.split() else "cmd"
        cmd_hash = hashlib.md5(cmd.encode()).hexdigest()[:8]
        
        if context:
            ctx_str = ",".join(f"{k}={v}" for k, v in sorted(context.items()))
            ctx_hash = hashlib.md5(ctx_str.encode()).hexdigest()[:6]
            return f"{engine}:{cmd_prefix}:{cmd_hash}@{ctx_hash}"
        return f"{engine}:{cmd_prefix}:{cmd_hash}"
    
    def _sanitize(self, s: str) -> str:
        """Sanitize string for filename use."""
        return re.sub(r'[^a-zA-Z0-9_-]', '_', s)[:20]
