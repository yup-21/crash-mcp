"""Command output persistence and retrieval."""
import re
import time
import json
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
    output_file: Optional[Path] = None  # None if not persisted to disk
    output_content: Optional[str] = None # Content if not persisted (small outputs)
    total_lines: int = 0
    timestamp: float = 0.0
    duration: float = 0.0     # Execution duration in seconds
    cached: bool = False
    is_error: bool = False    # True if output indicates an error


class CommandStore:
    """Persists command outputs and provides pagination/search."""
    
    def __init__(self, workdir: Path):
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        self._commands: Dict[str, CommandResult] = {}  # command_id -> result
        self._index = 0
        self._manifest_file = self.workdir / "manifest.json"
        self._load_manifest()
        logger.debug(f"CommandStore initialized at {self.workdir}")
    
    def save(self, engine: str, command: str, output: str, 
             context: Dict[str, str], is_error: bool = False,
             duration: float = 0.0, force_save: bool = False) -> CommandResult:
        """Persist command output, return result.
        
        Logic:
        - Save to file if:
          1. Output length > TRUNCATE_LINES (meaning we truncated it for initial response)
          2. Duration > COMMAND_SAVE_THRESHOLD_SECONDS (expensive to re-compute)
          3. force_save is True
        - Otherwise, store in memory (CommandResult.output_content)
        """
        command_id = self._make_id(engine, command, context)
        lines = output.splitlines()
        total_lines = len(lines)
        
        # Determine strict save criteria
        from crash_mcp.config import Config
        should_save = (
            force_save or 
            total_lines > Config.OUTPUT_TRUNCATE_LINES or 
            duration > Config.COMMAND_SAVE_THRESHOLD_SECONDS
        )
        
        # Check if already exists (update timestamp)
        if command_id in self._commands:
            existing = self._commands[command_id]
            
            if should_save:
                # Ensure we have a file path
                if not existing.output_file:
                    existing.output_file = self._generate_path(engine, command)
                
                try:
                    existing.output_file.write_text(output)
                    existing.output_content = None # Clear memory if saved to file
                except IOError as e:
                     logger.error(f"Failed to write output file: {e}")
                     # Fallback to memory
                     existing.output_content = output
                     existing.output_file = None
            else:
                # Store in memory
                existing.output_content = output
                # If it had a file before, we *could* delete it, but safer to leave or ignore
                # For simplicity, if it was file-based, we keep it file-based to avoid churn
                if existing.output_file and existing.output_file.exists():
                     pass # Keep existing file
                else:
                     existing.output_file = None

            existing.total_lines = total_lines
            existing.timestamp = time.time()
            existing.duration = duration
            existing.cached = False
            existing.is_error = is_error
            
            if existing.output_file:
                logger.debug(f"Updated command output file: {command_id} -> {existing.output_file}")
                self._save_manifest()
            
            return existing
        
        # New Entry
        output_file = None
        output_content = None
        
        if should_save:
            output_file = self._generate_path(engine, command)
            try:
                output_file.write_text(output)
            except IOError as e:
                logger.error(f"Failed to write output file: {e}")
                # Fallback
                output_content = output
                output_file = None
        else:
             output_content = output
        
        result = CommandResult(
            command_id=command_id,
            command=command,
            engine=engine,
            output_file=output_file,
            output_content=output_content,
            total_lines=total_lines,
            timestamp=time.time(),
            duration=duration,
            cached=False,
            is_error=is_error,
        )
        self._commands[command_id] = result
        if output_file:
            logger.debug(f"Saved command output to file: {command_id} -> {output_file}")
            self._save_manifest()
        else:
            logger.debug(f"Saved command output to memory: {command_id}")
        return result

    def _generate_path(self, engine: str, command: str) -> Path:
        """Generate unique filename."""
        self._index += 1
        cmd_sanitized = self._sanitize(command.strip().split()[0] if command.strip() else "cmd")
        filename = f"{self._index:04d}_{engine}_{cmd_sanitized}.txt"
        return self.workdir / filename
    
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
            if result.output_file and result.output_file.exists():
                lines = result.output_file.read_text().splitlines()
            elif result.output_content is not None:
                lines = result.output_content.splitlines()
            else:
                 raise ValueError("No content available for this command output")
        except IOError as e:
            logger.error(f"Failed to read output file: {e}")
            raise ValueError(f"Failed to read output: {e}")
        
        total = len(lines)
        selected = lines[offset:offset + limit]
        has_more = offset + limit < total
        return "\n".join(selected), len(selected), total, has_more
    
    def search(self, command_id: str, query: str, 
               context_lines: int = 3) -> List[Dict]:
        """Search output with regex, return matches with context.
        
        Note: Caps results at 20 matches to prevent massive context explosion.
        """
        result = self._commands.get(command_id)
        if not result:
            raise ValueError(f"Command not found: {command_id}")
        
        try:
            if result.output_file and result.output_file.exists():
                lines = result.output_file.read_text().splitlines()
            elif result.output_content is not None:
                lines = result.output_content.splitlines()
            else:
                 raise ValueError("No content available for this command output")
        except IOError as e:
            logger.error(f"Failed to read output file: {e}")
            raise ValueError(f"Failed to read output: {e}")
        
        try:
            pattern = re.compile(query, re.IGNORECASE)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern: {e}")
        
        matches = []
        limit = 20  # Hard limit to prevent context explosion
        
        for i, line in enumerate(lines):
            if pattern.search(line):
                matches.append({
                    "line_number": i + 1,
                    "context_before": lines[max(0, i-context_lines):i],
                    "line": line,
                    "context_after": lines[i+1:i+1+context_lines],
                })
                if len(matches) >= limit:
                    # Append a warning match to inform agent
                    matches.append({
                        "line_number": -1,
                        "context_before": [],
                        "line": f"[SYSTEM WARNING] Search result truncated. Found >{limit} matches. Please refine your query.",
                        "context_after": []
                    })
                    break
        
        logger.debug(f"Search '{query}' in {command_id}: {len(matches)} matches (limit: {limit})")
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

    def _load_manifest(self):
        """Load command index from manifest.json."""
        if not self._manifest_file.exists():
            return
            
        try:
            data = json.loads(self._manifest_file.read_text())
            for cid, info in data.items():
                # Reconstruct CommandResult
                output_file = self.workdir / info['output_file'] if info.get('output_file') else None
                
                # Check if file actually exists
                if output_file and not output_file.exists():
                    logger.warning(f"Manifest entry {cid} points to missing file {output_file}")
                    continue
                    
                # Validate essential fields
                cmd_str = info.get('command')
                engine_str = info.get('engine')
                
                if not cmd_str or not engine_str:
                    logger.warning(f"Skipping malformed manifest entry {cid}: missing command or engine")
                    continue

                self._commands[cid] = CommandResult(
                    command_id=cid,
                    command=cmd_str,
                    engine=engine_str,
                    output_file=output_file,
                    output_content=None, # Content not loaded into memory from manifest
                    total_lines=info.get('total_lines', 0),
                    timestamp=info.get('timestamp', 0),
                    duration=info.get('duration', 0.0),
                    cached=False,
                    is_error=info.get('is_error', False)
                )
                
                # Update index to avoid collision
                # filenames are like 0001_...
                if output_file:
                    try:
                        idx = int(output_file.name.split('_')[0])
                        self._index = max(self._index, idx)
                    except (ValueError, IndexError):
                        pass
                        
            logger.info(f"Loaded {len(self._commands)} entries from manifest")
        except Exception as e:
            logger.error(f"Failed to load manifest: {e}")

    def _save_manifest(self):
        """Save command index to manifest.json."""
        data = {}
        for cid, res in self._commands.items():
            # Only save persisted commands to manifest
            if res.output_file:
                data[cid] = {
                    "command": res.command,
                    "engine": res.engine,
                    "output_file": res.output_file.name,
                    "total_lines": res.total_lines,
                    "timestamp": res.timestamp,
                    "duration": res.duration,
                    "is_error": res.is_error
                }
        
        try:
            self._manifest_file.write_text(json.dumps(data, indent=2))
        except IOError as e:
            logger.error(f"Failed to write manifest: {e}")
