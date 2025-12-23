import logging
import uuid
import os
import click
from typing import Optional, Dict
from mcp.server.fastmcp import FastMCP

from crash_mcp.session import CrashSession
from crash_mcp.discovery import CrashDiscovery
from crash_mcp.config import Config
from crash_mcp.unified_session import UnifiedSession
from crash_mcp.kb import get_retriever


# Configure logging
logging.basicConfig(level=getattr(logging, Config.LOG_LEVEL.upper()), 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.FileHandler("server.log"),
                        logging.StreamHandler()
                    ])
logger = logging.getLogger("crash-mcp")

# Initialize Server
mcp = FastMCP("crash-mcp")

# State management - unified session storage
sessions: Dict[str, UnifiedSession] = {}
last_session_id: Optional[str] = None


# --- Tools ---

@mcp.tool()
def list_crash_dumps(search_path: str = Config.CRASH_SEARCH_PATH) -> str:
    """Scans for crash dumps in the specified directory (recursive)."""
    logger.info(f"Listing crash dumps in {search_path}")
    try:
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
        
        logger.info(f"Returning {len(output)} lines of output")
        return "\n".join(output)
    except Exception as e:
        logger.error(f"Error in list_crash_dumps: {e}", exc_info=True)
        return f"Error scanning for dumps: {str(e)}"


@mcp.tool()
def start_session(vmcore_path: str, vmlinux_path: str, 
                  ssh_host: Optional[str] = None, ssh_user: Optional[str] = None) -> str:
    """Starts analysis session. Requires vmcore and vmlinux paths. Returns session ID."""
    global last_session_id
    
    # Validation
    if not ssh_host and not os.path.exists(vmcore_path):
        return f"Error: Dump file not found locally at {vmcore_path} and no remote host specified."

    session_id = str(uuid.uuid4())
    logger.info(f"Starting Session {session_id} for {vmcore_path} (Remote: {ssh_host})")
    
    try:
        session = UnifiedSession(vmcore_path, vmlinux_path, 
                               remote_host=ssh_host, remote_user=ssh_user)
        session.start()
        
        sessions[session_id] = session
        last_session_id = session_id
        
        return f"Session started successfully. ID: {session_id}\n(Wraps both 'crash' and 'drgn' engines. Commands are automatically routed.)"
    except Exception as e:
        logger.error(f"Failed to start session: {e}")
        return f"Failed to start session: {str(e)}"


@mcp.tool()
def run_crash_command(command: str, session_id: Optional[str] = None, truncate: bool = True) -> str:
    """Runs crash utility command (e.g., sys, bt, log, ps, files, vm, kmem)."""
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
        return session.execute_command(f"crash:{command}", truncate=truncate)
    except Exception as e:
        return f"Error executing command: {str(e)}"


@mcp.tool()
def run_drgn_command(command: str, session_id: Optional[str] = None, truncate: bool = True) -> str:
    """Runs drgn Python code (e.g., prog.crashed_thread(), prog['variable'])."""
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
        return session.execute_command(f"drgn:{command}", truncate=truncate)
    except Exception as e:
        return f"Error executing command: {str(e)}"


@mcp.tool()
def stop_session(session_id: Optional[str] = None) -> str:
    """Terminates an active session."""
    global last_session_id
    
    target_id = session_id or last_session_id
    
    if not target_id:
        return "Error: No session specified and no active default session."
    
    if target_id not in sessions:
        return f"Error: Session ID {target_id} not found."
        
    session = sessions[target_id]
    session.stop()
    del sessions[target_id]
    
    if last_session_id == target_id:
        last_session_id = None
        
    return f"Session {target_id} closed."


@mcp.tool()
def get_sys_info(session_id: Optional[str] = None) -> str:
    """Convenience tool to get system info (runs 'sys' command)."""
    return run_crash_command("sys", session_id)


# --- Knowledge Base Tools ---

@mcp.tool()
def kb_search_method(panic_text: str) -> str:
    """Search analysis methods by panic/error text. Returns matching methods with steps."""
    retriever = get_retriever("knowledge/methods")
    results = retriever.search_method(panic_text, top_k=3)
    
    if not results:
        return "No matching analysis methods found."
    
    output = []
    for r in results:
        output.append(f"## {r['name']} (score: {r['score']})")
        output.append(f"Description: {r['description']}")
        if r.get('matched_patterns'):
            output.append(f"Matched: {', '.join(r['matched_patterns'])}")
        output.append("Steps:")
        for step in r['steps']:
            output.append(f"  - {step['command']} ({step['purpose']})")
        output.append("")
    
    return "\n".join(output)


@mcp.tool()
def kb_list_methods() -> str:
    """List all available analysis methods."""
    retriever = get_retriever("knowledge/methods")
    methods = retriever.list_methods()
    
    output = ["Available analysis methods:"]
    for m in methods:
        output.append(f"  - {m['id']}: {m['name']}")
    return "\n".join(output)


@mcp.tool()
def kb_get_next_steps(output_text: str, current_method: str) -> str:
    """Suggest next analysis methods based on current output."""
    retriever = get_retriever("knowledge/methods")
    suggestions = retriever.get_next_methods(output_text, current_method)
    
    if not suggestions:
        return "No further analysis methods suggested."
    
    output = ["Suggested next methods:"]
    for s in suggestions:
        output.append(f"  - {s['name']} (reason: {s['reason']})")
    return "\n".join(output)


def main():
    cli()


@click.command()
@click.option('--transport', type=click.Choice(['stdio', 'sse']), default='stdio', help='Transport mode')
@click.option('--port', type=int, default=8000, help='Port for SSE mode')
@click.option('--host', default='0.0.0.0', help='Host for SSE mode')
def cli(transport, port, host):
    if transport == 'sse':
        logger.info(f"Starting SSE server on {host}:{port}")
        mcp.settings.port = port
        mcp.settings.host = host
        mcp.run(transport='sse')
    else:
        logger.info("Starting Stdio server")
        mcp.run(transport='stdio')

if __name__ == "__main__":
    cli()
