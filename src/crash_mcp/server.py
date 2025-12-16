import logging
import uuid
import os
from typing import Optional, List, Dict
from mcp.server.fastmcp import FastMCP

from crash_mcp.session import CrashSession
from crash_mcp.discovery import CrashDiscovery
from crash_mcp.config import Config

# Configure logging
logging.basicConfig(level=getattr(logging, Config.LOG_LEVEL.upper()), 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("crash-mcp")

# Initialize Server
mcp = FastMCP("crash-mcp")

# State management
sessions: Dict[str, CrashSession] = {}
last_session_id: Optional[str] = None

# --- Tools ---

@mcp.tool()
def list_crash_dumps(search_path: str = Config.CRASH_SEARCH_PATH) -> str:
    """
    Scans for crash dumps in the specified directory (recursive).
    Returns a formatted string list of found dumps.
    """
    logger.info(f"Listing crash dumps in {search_path}")
    dumps = CrashDiscovery.find_dumps([search_path])
    
    if not dumps:
        return "No crash dumps found."
    
    # Sort by modification time (newest first)
    dumps.sort(key=lambda x: x['modified'], reverse=True)
    
    # Limit to top 10 to save tokens
    total_count = len(dumps)
    limit = 10
    dumps = dumps[:limit]
        
    output = [f"Found {total_count} crash dumps (showing top {limit}):"]
    for d in dumps:
        output.append(f"- {d['path']} (Size: {d['size']} bytes)")
    
    if total_count > limit:
        output.append(f"... and {total_count - limit} more.")
    
    return "\n".join(output)

def _start_session_internal(dump_path: str, kernel_path: Optional[str] = None) -> str:
    """Helper to start session and update global state."""
    global last_session_id
    
    if not os.path.exists(dump_path):
        return f"Error: Dump file not found at {dump_path}"
        
    if not kernel_path:
        # Try to auto-match
        kernel_path = CrashDiscovery.match_kernel(dump_path, [os.path.dirname(dump_path)])
        if kernel_path:
            logger.info(f"Auto-matched kernel: {kernel_path}")
        else:
            logger.warning("No matching kernel found automatically.")
    
    session_id = str(uuid.uuid4())
    logger.info(f"Starting session {session_id} for {dump_path}")
    
    try:
        session = CrashSession(dump_path, kernel_path)
        session.start()
        sessions[session_id] = session
        last_session_id = session_id # Update default session
        return session_id
    except Exception as e:
        logger.error(f"Failed to start session: {e}")
        raise e

@mcp.tool()
def start_crash_session(dump_path: str, kernel_path: Optional[str] = None) -> str:
    """
    Starts a new interactive crash analysis session for the given dump.
    If kernel_path is not provided, attempts to find a matching kernel automatically.
    Returns the Session ID.
    """
    try:
        session_id = _start_session_internal(dump_path, kernel_path)
        return f"Session started successfully. Session ID: {session_id}"
    except Exception as e:
        return f"Error starting crash session: {str(e)}"

@mcp.tool()
def analyze_target(vmcore_path: str, vmlinux_path: str) -> str:
    """
    Starts a crash analysis session with explicit vmcore and vmlinux paths.
    This sets the default active session, so subsequent commands (run_crash_command) 
    don't need to specify a session_id.
    """
    try:
        session_id = _start_session_internal(vmcore_path, vmlinux_path)
        return f"Analysis started for {vmcore_path}. Session ID: {session_id}. You can now run commands."
    except Exception as e:
        return f"Failed to start analysis: {str(e)}"

@mcp.tool()
def run_crash_command(command: str, session_id: Optional[str] = None, truncate: bool = True) -> str:
    """
    Executes a command in an active crash session.
    If session_id is omitted, uses the most recently started session.
    
    Args:
        command: The crash command to run
        session_id: Optional explicit session ID
        truncate: Whether to truncate long output (default: True). Set to False for full output.
    """
    target_id = session_id or last_session_id
    
    if not target_id:
        return "Error: No session specified and no active default session."
        
    if target_id not in sessions:
        return f"Error: Session ID {target_id} not found."
    
    session = sessions[target_id]
    if not session.is_active():
        del sessions[target_id]
        return "Error: Session is no longer active."
        
    try:
        output = session.execute_command(command, truncate=truncate)
        return output
    except Exception as e:
        return f"Error executing command: {str(e)}"

@mcp.tool()
def stop_crash_session(session_id: str) -> str:
    """
    Terminates an active crash session.
    """
    if session_id not in sessions:
        return f"Error: Session ID {session_id} not found."
        
    session = sessions[session_id]
    session.close()
    del sessions[session_id]
    return f"Session {session_id} closed."

@mcp.tool()
def get_sys_info(session_id: Optional[str] = None) -> str:
    """
    Convenience tool to get system info (runs 'sys' command).
    Uses default session if session_id is not provided.
    """
    return run_crash_command("sys", session_id)

def main():
    mcp.run()

if __name__ == "__main__":
    main()
