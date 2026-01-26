"""Tool call logging with tracing support.

Provides a wrapper to log all tool calls with input/output to workdir.
"""
import functools
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Any

from crash_mcp.config import Config

logger = logging.getLogger("crash-mcp")

# Tool call log file handle
_tool_log_file = None


def _get_tool_log_path() -> Path:
    """Get the tool call log file path."""
    workdir = Path(Config.SESSION_WORKDIR_BASE)
    workdir.mkdir(parents=True, exist_ok=True)
    return workdir / "tool_calls.jsonl"


def _init_tool_log():
    """Initialize tool call log file."""
    global _tool_log_file
    if _tool_log_file is None and Config.LOG_TOOL_CALLS:
        log_path = _get_tool_log_path()
        _tool_log_file = open(log_path, "a", buffering=1)  # Line buffered
        logger.info(f"Tool call logging enabled: {log_path}")


def _log_tool_call(tool_name: str, args: dict, result: Any, duration_ms: float, error: str = None):
    """Log a single tool call to the JSONL file."""
    global _tool_log_file
    
    if not Config.LOG_TOOL_CALLS:
        return
    
    if _tool_log_file is None:
        _init_tool_log()
    
    if _tool_log_file is None:
        return
    
    # Truncate large outputs
    result_str = str(result)
    if len(result_str) > 2000:
        result_str = result_str[:2000] + f"... (truncated, total {len(result_str)} chars)"
    
    entry = {
        "timestamp": datetime.now().isoformat(),
        "tool": tool_name,
        "args": args,
        "duration_ms": round(duration_ms, 2),
    }
    
    if error:
        entry["error"] = error
    else:
        entry["result"] = result_str
    
    try:
        _tool_log_file.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"Failed to log tool call: {e}")


def logged_tool(func: Callable) -> Callable:
    """Decorator to wrap tool functions with logging.
    
    Usage:
        @logged_tool
        def my_tool(arg1, arg2):
            ...
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        tool_name = func.__name__
        
        # Build args dict for logging (skip Context objects)
        logged_args = {}
        import inspect
        sig = inspect.signature(func)
        params = list(sig.parameters.keys())
        
        for i, arg in enumerate(args):
            if i < len(params):
                param_name = params[i]
                # Skip Context type args
                if hasattr(arg, 'info') and hasattr(arg, 'report_progress'):
                    continue
                logged_args[param_name] = arg
        
        for key, value in kwargs.items():
            if hasattr(value, 'info') and hasattr(value, 'report_progress'):
                continue
            logged_args[key] = value
        
        start_time = time.perf_counter()
        error_msg = None
        result = None
        
        try:
            result = func(*args, **kwargs)
            return result
        except Exception as e:
            error_msg = str(e)
            raise
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            _log_tool_call(tool_name, logged_args, result, duration_ms, error_msg)
    
    return wrapper


def close_tool_log():
    """Close the tool call log file."""
    global _tool_log_file
    if _tool_log_file:
        _tool_log_file.close()
        _tool_log_file = None
