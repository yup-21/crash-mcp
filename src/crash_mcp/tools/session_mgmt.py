"""Session management tools for crash-mcp."""
import os
import uuid
import logging
from typing import Optional
from mcp.server.fastmcp import FastMCP

from crash_mcp.discovery import CrashDiscovery
from crash_mcp.config import Config
from crash_mcp.common.unified_session import UnifiedSession
import crash_mcp.context as context

logger = logging.getLogger("crash-mcp")


def list_crash_dumps(search_path: str = Config.CRASH_SEARCH_PATH) -> str:
    """Scans for crash dumps in the specified directory (recursive)."""
    logger.info(f"Listing crash dumps in {search_path}")
    try:
        dumps = CrashDiscovery.find_dumps([search_path])
        
        if not dumps:
            return "No crash dumps found."
        
        # Sort by modification time (newest first)
        dumps.sort(key=lambda x: x['modified'], reverse=True)
        
        # Limit to top 10
        total_count = len(dumps)
        limit = 10
        dumps = dumps[:limit]
            
        output = [f"Found {total_count} crash dumps (showing top {limit}):"]
        for d in dumps:
            info = CrashDiscovery.get_dump_info(d['path'])
            if info:
                info_str = f"  Kernel: {info['kernel_version']}, Arch: {info['arch']}, Host: {info['hostname']}"
            else:
                arch_info = CrashDiscovery.get_arch_from_dump(d['path'])
                info_str = f"  Arch: {arch_info['machine']}" if arch_info else ""
            
            size_mb = d['size'] / (1024 * 1024)
            output.append(f"- {d['path']} ({size_mb:.1f} MB)")
            if info_str:
                output.append(info_str)
        
        if total_count > limit:
            output.append(f"... and {total_count - limit} more.")
        
        return "\n".join(output)
    except Exception as e:
        logger.error(f"Error in list_crash_dumps: {e}", exc_info=True)
        return f"Error scanning for dumps: {str(e)}"


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
    # Parse crash_args
    args_list = crash_args.split(',') if crash_args else []
    
    # Validation
    if not ssh_host and not os.path.exists(vmcore_path):
        return f"Error: Dump file not found locally at {vmcore_path} and no remote host specified."

    # Check version match
    version_warning = ""
    if not ssh_host and os.path.exists(vmcore_path) and os.path.exists(vmlinux_path):
        match_result = CrashDiscovery.check_version_match(vmcore_path, vmlinux_path)
        if not match_result.get('match') and match_result.get('vmcore_version'):
            version_warning = f"\n⚠️ {match_result['message']}"

    session_id = str(uuid.uuid4())
    logger.info(f"Starting Session {session_id} for {vmcore_path}")
    
    try:
        session = UnifiedSession(vmcore_path, vmlinux_path, 
                               remote_host=ssh_host, remote_user=ssh_user,
                               crash_args=args_list)
        session.start()
        
        context.sessions[session_id] = session
        context.last_session_id = session_id
        
        # Get architecture and binary info
        extra_info = []
        if session.crash_session:
            detected_arch = session.crash_session.detected_arch
            binary_path = session.crash_session.binary_path
            if detected_arch:
                extra_info.append(f"Detected architecture: {detected_arch}")
                extra_info.append(f"Using crash binary: {binary_path}")
        
        # Get vmcore info
        if not ssh_host:
            dump_info = CrashDiscovery.get_dump_info(vmcore_path)
            if dump_info:
                extra_info.append(f"Kernel version: {dump_info['kernel_version']}")
                extra_info.append(f"Hostname: {dump_info['hostname']}")
        
        info_str = "\n".join(extra_info)
        if info_str:
            info_str = "\n" + info_str
        
        return f"Session started successfully. ID: {session_id}{info_str}{version_warning}\n(Wraps both 'crash' and 'drgn' engines.)"
    except Exception as e:
        logger.error(f"Failed to start session: {e}")
        return f"Failed to start session: {str(e)}"


def run_crash_command(command: str, session_id: Optional[str] = None, truncate: bool = True) -> str:
    """Runs crash utility command (e.g., sys, bt, log, ps, files, vm, kmem)."""
    target_id = session_id or context.last_session_id
    
    if not target_id:
        return "Error: No session specified and no active default session."
    
    if target_id not in context.sessions:
        return f"Error: Session ID {target_id} not found."
    
    session = context.sessions[target_id]
    if not session.is_active():
        del context.sessions[target_id]
        return "Error: Session is no longer active."
        
    try:
        return session.execute_command(f"crash:{command}", truncate=truncate)
    except Exception as e:
        return f"Error executing command: {str(e)}"


def run_drgn_command(command: str, session_id: Optional[str] = None, truncate: bool = True) -> str:
    """Runs drgn Python code (e.g., prog.crashed_thread(), prog['variable'])."""
    target_id = session_id or context.last_session_id
    
    if not target_id:
        return "Error: No session specified and no active default session."
    
    if target_id not in context.sessions:
        return f"Error: Session ID {target_id} not found."
    
    session = context.sessions[target_id]
    if not session.is_active():
        del context.sessions[target_id]
        return "Error: Session is no longer active."
        
    try:
        return session.execute_command(f"drgn:{command}", truncate=truncate)
    except Exception as e:
        return f"Error executing command: {str(e)}"


def stop_session(session_id: Optional[str] = None) -> str:
    """Terminates an active session."""
    target_id = session_id or context.last_session_id
    
    if not target_id:
        return "Error: No session specified and no active default session."
    
    if target_id not in context.sessions:
        return f"Error: Session ID {target_id} not found."
        
    session = context.sessions[target_id]
    session.stop()
    del context.sessions[target_id]
    
    if context.last_session_id == target_id:
        context.last_session_id = None
        
    return f"Session {target_id} closed."


def get_sys_info(session_id: Optional[str] = None) -> str:
    """Convenience tool to get system info (runs 'sys' command)."""
    return run_crash_command("sys", session_id)


def register(mcp: FastMCP):
    """Register session management tools with MCP server."""
    mcp.tool()(list_crash_dumps)
    mcp.tool()(start_session)
    mcp.tool()(run_crash_command)
    mcp.tool()(run_drgn_command)
    mcp.tool()(stop_session)
    # mcp.tool()(get_sys_info)  # Hidden: too simple, use run_crash_command("sys") instead
