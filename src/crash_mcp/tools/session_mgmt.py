"""Session management tools for crash-mcp."""
import os
import logging
import datetime
from typing import Optional
from mcp.server.fastmcp import FastMCP, Context

from crash_mcp.common.vmcore_discovery import CrashDiscovery
from crash_mcp.config import Config
from crash_mcp.common.unified_session import UnifiedSession
from crash_mcp.common.command_store import CommandResult
from crash_mcp.tools.utils import json_response, get_session
import crash_mcp.context as context

logger = logging.getLogger("crash-mcp")


def _format_command_response(result: CommandResult, max_lines: int) -> str:
    """Format command response with truncation and state info."""
    if result.output_file is None:
        # Fallback for sessions without workdir
        return json_response("success", {
            "output": "",
            "command_id": result.command_id,
            "state": {"total_lines": result.total_lines, "truncated": False},
        })
    
    lines = result.output_file.read_text().splitlines()
    total = len(lines)
    
    if total <= max_lines:
        return json_response("success", {
            "output": "\n".join(lines),
            "command_id": result.command_id,
            "state": {
                "total_lines": total,
                "returned_lines": total,
                "truncated": False
            },
        })
    
    return json_response("success", {
        "output": "\n".join(lines[:max_lines]),
        "command_id": result.command_id,
        "state": {
            "total_lines": total,
            "returned_lines": max_lines,
            "truncated": True,
            "remaining": total - max_lines,
        },
    })


def list_crash_dumps(search_path: str = Config.CRASH_SEARCH_PATH) -> str:
    """Scan for vmcore files. Returns paths and modification times of recent dumps."""
    logger.info(f"Listing crash dumps in {search_path}")
    try:
        dumps = CrashDiscovery.find_dumps([search_path])
        
        if not dumps:
            return json_response("success", [])
        
        dumps.sort(key=lambda x: x['modified'], reverse=True)
        dumps = dumps[:10]
            
        result = []
        for d in dumps:
            mod_time = datetime.datetime.fromtimestamp(d['modified']).strftime('%Y-%m-%d %H:%M')
            result.append({"path": d['path'], "modified": mod_time})
        
        return json_response("success", result)
    except Exception as e:
        logger.error(f"Error in list_crash_dumps: {e}", exc_info=True)
        return json_response("error", error=f"Error scanning for dumps: {str(e)}")


def open_vmcore_session(ctx: Context, vmcore_path: str, vmlinux_path: str, 
                  ssh_host: Optional[str] = None, ssh_user: Optional[str] = None,
                  crash_args: Optional[str] = None) -> str:
    """Open vmcore dump for kernel analysis. Returns session_id for use in other tools.
    """
    ctx.info(f"Start session requested for {vmcore_path}")
    ctx.report_progress(0, 100, "Initializing session request")
    
    args_list = crash_args.split(',') if crash_args else []
    
    # Validation
    if not ssh_host and not os.path.exists(vmcore_path):
        return json_response("error", error=f"Dump file not found locally at {vmcore_path} and no remote host specified.")

    # Check version match
    version_warning = ""
    if not ssh_host and os.path.exists(vmcore_path) and os.path.exists(vmlinux_path):
        ctx.report_progress(10, 100, "Checking kernel version match")
        match_result = CrashDiscovery.check_version_match(vmcore_path, vmlinux_path)
        if not match_result.get('match') and match_result.get('vmcore_version'):
            version_warning = match_result['message']

    # Use SessionManager for deduplication
    ctx.report_progress(15, 100, "Checking existing sessions")
    session_id, info, is_new = context.session_manager.get_or_create(vmcore_path, vmlinux_path)
    
    if not is_new:
        # Session already exists for this vmcore
        if session_id in context.sessions:
            context.session_manager.acquire(session_id)  # Increment ref count
            context.last_session_id = session_id
            result = {
                "session_id": session_id,
            }
            if version_warning:
                result["warning"] = version_warning
            
            ctx.report_progress(100, 100, "Session ready")
            return json_response("success", result)
        # Session was registered but not started (shouldn't happen normally)
        # Fall through to create it
    
    logger.info(f"Starting Session {session_id} for {vmcore_path}")
    
    try:
        ctx.report_progress(20, 100, "Preparing analysis environment")
        session = UnifiedSession(
            vmcore_path, vmlinux_path, 
            remote_host=ssh_host, remote_user=ssh_user,
            crash_args=args_list,
            workdir=info.workdir  # Pass workdir to session
        )
        
        def on_progress_cb(p: float, msg: str):
            # Scale session progress (0-100) to overall progress (20-100)
            scaled = 20 + (p / 100.0) * 80
            ctx.report_progress(scaled, 100, msg)
            
        session.start(on_progress=on_progress_cb)
        
        context.sessions[session_id] = session
        context.session_manager.acquire(session_id)  # Increment ref count
        context.last_session_id = session_id
        
        result = {
            "session_id": session_id,
        }
        if version_warning:
            result["warning"] = version_warning
            
        return json_response("success", result)
    except Exception as e:
        logger.error(f"Failed to start session: {e}")
        context.session_manager.remove_session(session_id)
        return json_response("error", error=f"Failed to start session: {str(e)}")


def run_crash_command(command: str, session_id: Optional[str] = None, 
                      force_execute: bool = False) -> str:
    """Execute crash utility command on vmcore.
    
    Common commands: bt (backtrace), sys (system info), ps (processes), 
    log (dmesg), kmem (memory info), files, net, mount.
    
    Also supports PyKdump extensions if installed.
    """
    try:
        target_id, session = get_session(session_id)
    except ValueError as e:
        return json_response("error", error=str(e))
        
    try:
        result = session.execute_with_store(f"crash:{command}", force=force_execute)
        return _format_command_response(result, Config.OUTPUT_TRUNCATE_LINES)
    except Exception as e:
        logger.error(f"Error executing crash command: {e}")
        return json_response("error", error=str(e))


def run_drgn_command(command: str, session_id: Optional[str] = None,
                     force_execute: bool = False) -> str:
    """Execute drgn Python code on vmcore.
    
    The 'prog' object is pre-initialized for direct use.
    
    Examples:
        prog['init_task'].comm
        list(prog.tasks())
        prog.type('struct task_struct')
    """
    try:
        target_id, session = get_session(session_id)
    except ValueError as e:
        return json_response("error", error=str(e))
        
    try:
        result = session.execute_with_store(f"drgn:{command}", force=force_execute)
        return _format_command_response(result, Config.OUTPUT_TRUNCATE_LINES)
    except Exception as e:
        logger.error(f"Error executing drgn command: {e}")
        return json_response("error", error=str(e))


def run_pykdump_command(code: str, session_id: Optional[str] = None,
                        force_execute: bool = False) -> str:
    """Execute PyKdump command (e.g., crashinfo, xportshow, netstat)."""
    try:
        target_id, session = get_session(session_id)
    except ValueError as e:
        return json_response("error", error=str(e))
        
    try:
        result = session.execute_with_store(f"pykdump:{code}", force=force_execute)
        return _format_command_response(result, Config.OUTPUT_TRUNCATE_LINES)
    except Exception as e:
        logger.error(f"Error executing pykdump command: {e}")
        return json_response("error", error=str(e))


def close_vmcore_session(session_id: Optional[str] = None) -> str:
    """Close vmcore analysis session and release resources.
    
    Args:
        session_id: Session to close (uses last session if omitted)
    """
    try:
        target_id, session = get_session(session_id)
    except ValueError as e:
        return json_response("error", error=str(e))
    
    # Release reference
    ref_count = context.session_manager.release(target_id)
    
    if ref_count > 0:
        # Other references exist, session stays active
        return json_response("success", {"message": "Session released"})
    
    # No more references, actually close the session
    session.stop()
    del context.sessions[target_id]
    context.session_manager.remove_session(target_id)
    
    if context.last_session_id == target_id:
        context.last_session_id = None
        
    return json_response("success", {"message": "Session closed"})


def register(mcp: FastMCP):
    """Register session management tools with MCP server."""
    from crash_mcp.tools.tool_logging import logged_tool
    
    # mcp.tool()(list_crash_dumps)  # Hidden: use open_vmcore_session with known path
    mcp.tool()(logged_tool(open_vmcore_session))
    mcp.tool()(logged_tool(run_crash_command))
    mcp.tool()(logged_tool(run_drgn_command))
    # mcp.tool()(run_pykdump_command)  # Hidden: use run_crash_command with pykdump extensions
    mcp.tool()(logged_tool(close_vmcore_session))
