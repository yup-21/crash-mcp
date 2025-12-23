import logging
import uuid
import os
from typing import Optional, List, Dict
from mcp.server.fastmcp import FastMCP

from crash_mcp.session import CrashSession
from crash_mcp.discovery import CrashDiscovery
from crash_mcp.config import Config
from crash_mcp.drgn_session import DrgnSession


# Configure logging
logging.basicConfig(level=getattr(logging, Config.LOG_LEVEL.upper()), 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("crash-mcp")

# Initialize Server
mcp = FastMCP("crash-mcp")

# State management
# State management
sessions: Dict[str, CrashSession] = {}
drgn_sessions: Dict[str, DrgnSession] = {}
last_session_id: Optional[str] = None
last_drgn_session_id: Optional[str] = None


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
    Starts both crash and drgn analysis sessions for the target.
    This sets the default active sessions for both tools.
    """
    results = []
    
    # Start Crash Session
    try:
        crash_id = _start_session_internal(vmcore_path, vmlinux_path)
        results.append(f"Crash Session: Started (ID: {crash_id})")
    except Exception as e:
        results.append(f"Crash Session: Failed ({str(e)})")
        
    # Start Drgn Session
    try:
        drgn_id = _start_drgn_session_internal(vmcore_path, vmlinux_path)
        results.append(f"Drgn Session: Started (ID: {drgn_id})")
    except Exception as e:
        results.append(f"Drgn Session: Failed ({str(e)})")
        
    return "\n".join(results)


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

# --- Drgn Tools ---

def _start_drgn_session_internal(dump_path: str, kernel_path: Optional[str] = None) -> str:
    """Helper to start drgn session and update global state."""
    global last_drgn_session_id
    
    if not os.path.exists(dump_path):
        return f"Error: Dump file not found at {dump_path}"
        
    session_id = str(uuid.uuid4())
    logger.info(f"Starting drgn session {session_id} for {dump_path}")
    
    try:
        session = DrgnSession(dump_path, kernel_path)
        session.start()
        drgn_sessions[session_id] = session
        last_drgn_session_id = session_id 
        return session_id
    except Exception as e:
        logger.error(f"Failed to start drgn session: {e}")
        raise e

@mcp.tool()
def start_drgn_session(dump_path: str, kernel_path: Optional[str] = None) -> str:
    """
    Starts a new interactive drgn analysis session for the given dump.
    Returns the Session ID.
    Notes:
    - drgn requires debug symbols (vmlinux). If kernel_path is usually required unless drgn can find it automatically.
    """
    try:
        session_id = _start_drgn_session_internal(dump_path, kernel_path)
        return f"Drgn session started successfully. Session ID: {session_id}"
    except Exception as e:
        return f"Error starting drgn session: {str(e)}"

@mcp.tool()
def run_drgn_command(command: str, session_id: Optional[str] = None, truncate: bool = True) -> str:
    """
    Executes a python command in an active drgn session.
    If session_id is omitted, uses the most recently started drgn session.
    """
    target_id = session_id or last_drgn_session_id
    
    if not target_id:
        return "Error: No drgn session specified and no active default session."
        
    if target_id not in drgn_sessions:
        return f"Error: Drgn Session ID {target_id} not found."
    
    session = drgn_sessions[target_id]
    if not session.is_active():
        del drgn_sessions[target_id]
        return "Error: Session is no longer active."
        
    try:
        output = session.execute_command(command, truncate=truncate)
        return output
    except Exception as e:
        return f"Error executing command: {str(e)}"


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
