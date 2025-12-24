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
from crash_mcp.unified_session import UnifiedSession
from crash_mcp.kb import get_retriever, get_layered_retriever
import json


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
                  ssh_host: Optional[str] = None, ssh_user: Optional[str] = None,
                  crash_args: Optional[str] = None) -> str:
    """Starts analysis session. Requires vmcore and vmlinux paths. Returns session ID.
    
    Args:
        vmcore_path: Path to vmcore dump file
        vmlinux_path: Path to vmlinux with debug symbols
        ssh_host: Optional remote host for SSH connection
        ssh_user: Optional SSH username
        crash_args: Optional extra crash args as comma-separated string (e.g. "-s,--mod,/path")
    """
    global last_session_id
    
    # Parse crash_args from comma-separated string to list
    args_list = crash_args.split(',') if crash_args else []
    
    # Validation
    if not ssh_host and not os.path.exists(vmcore_path):
        return f"Error: Dump file not found locally at {vmcore_path} and no remote host specified."

    session_id = str(uuid.uuid4())
    logger.info(f"Starting Session {session_id} for {vmcore_path} (Remote: {ssh_host}, Args: {args_list})")
    
    try:
        session = UnifiedSession(vmcore_path, vmlinux_path, 
                               remote_host=ssh_host, remote_user=ssh_user,
                               crash_args=args_list)
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


def _get_kb_base_dir() -> str:
    """Get absolute path to KB base directory."""
    base = Config.KB_BASE_DIR
    if base and os.path.isabs(base):
        return base
    # Default: project root
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(project_root, base) if base else project_root


def _get_methods_dir() -> str:
    return os.path.join(_get_kb_base_dir(), 'knowledge', 'methods')


def _get_data_dir() -> str:
    return os.path.join(_get_kb_base_dir(), 'data', 'chroma')


# --- Legacy KB Tools removed (kb_search_case, kb_save_case) ---
# Use CaseNode-based tools: kb_match_or_save_node, kb_search_subproblem


# --- Agent Tools (Layered KB) ---

@mcp.tool()
def kb_search_symptom(query: str) -> str:
    """[L1] Search Symptom Library (Vector+Keyword) for matching methods."""
    retriever = get_layered_retriever(_get_methods_dir(), _get_data_dir())
    results = retriever.search_symptom(query, top_k=3)
    
    if not results:
        return "No matching symptoms/methods found."
        
    output = []
    for r in results:
        output.append(f"## Protocol: {r['name']} (Score: {r['score']:.2f})")
        output.append(f"ID: {r['id']}")
        output.append(f"Source: {r.get('source', 'unknown')}")
        output.append("Steps:")
        for s in r['steps']:
            output.append(f"  - {s['command']}")
        output.append("")
    return "\n".join(output)


@mcp.tool()
def kb_analyze_method(method_id: str) -> str:
    """[L2] Execute Analysis Method and return structured context.
    Returns JSON string with commands to run and expected outputs."""
    retriever = get_layered_retriever(_get_methods_dir(), _get_data_dir())
    method_data = retriever.analyze_method(method_id)
    return json.dumps(method_data, indent=2)


@mcp.tool()
def kb_search_subproblem(query: str, context: str) -> str:
    """[L3] Search for sub-problems based on context. 
    Context should be a JSON string of findings."""
    try:
        ctx_dict = json.loads(context)
    except:
        ctx_dict = {"raw": context}
        
    retriever = get_layered_retriever(_get_methods_dir(), _get_data_dir())
    hits = retriever.search_subproblem(query, ctx_dict)
    
    if not hits:
        return "No known sub-problems found."
        
    return json.dumps(hits, indent=2)


@mcp.tool()
def kb_match_or_save_node(fingerprint: str, data: str) -> str:
    """[L3] Match existing Case Node or save new one.
    Data should be JSON string."""
    try:
        data_dict = json.loads(data)
    except:
        return "Error: Data must be valid JSON"
        
    retriever = get_layered_retriever(_get_methods_dir(), _get_data_dir())
    node_id = retriever.match_or_save_node(fingerprint, data_dict)
    return f"Node Ref: {node_id}"


@mcp.tool()
def kb_run_workflow(panic_text: str, session_id: Optional[str] = None) -> str:
    """[Workflow] Start/Continue analysis workflow. 
    Stateful orchestration of the analysis loop."""
    from crash_mcp.kb.workflow import quick_start
    
    res = quick_start(panic_text, methods_dir=_get_methods_dir())
    return json.dumps(res, indent=2)

# kb_update_workflow removed: Agent manages state directly via atomic tools

@mcp.tool()
def kb_mark_node_failed(node_id: str) -> str:
    """[L3] Mark a case node as failed/dead-end for negative feedback."""
    retriever = get_layered_retriever(_get_methods_dir(), _get_data_dir())
    success = retriever.mark_node_failed(node_id)
    if success:
        return f"Node {node_id} marked as failed."
    return f"Error: Node {node_id} not found."

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
