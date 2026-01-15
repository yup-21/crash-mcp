"""Session management tools for crash-mcp."""
import os
import uuid
import logging
from typing import Optional
from mcp.server.fastmcp import FastMCP

from crash_mcp.discovery import CrashDiscovery
from crash_mcp.config import Config
import datetime
from crash_mcp.common.unified_session import UnifiedSession
import crash_mcp.context as context

import json
import logging

logger = logging.getLogger("crash-mcp")

def _json_response(status: str, result=None, error=None) -> str:
    """Helper to format JSON response."""
    response = {"status": status}
    if result is not None:
        response["result"] = result
    if error is not None:
        response["error"] = error
    return json.dumps(response, ensure_ascii=False)


def list_crash_dumps(search_path: str = Config.CRASH_SEARCH_PATH) -> str:
    """扫描 vmcore 文件。"""
    logger.info(f"Listing crash dumps in {search_path}")
    try:
        dumps = CrashDiscovery.find_dumps([search_path])
        
        if not dumps:
            return _json_response("success", [])
        
        # Sort by modification time (newest first)
        dumps.sort(key=lambda x: x['modified'], reverse=True)
        
        # Limit to top 10
        limit = 10
        dumps = dumps[:limit]
            
        result = []
        for d in dumps:
            mod_time = datetime.datetime.fromtimestamp(d['modified']).strftime('%Y-%m-%d %H:%M')
            result.append({"path": d['path'], "modified": mod_time})
        
        return _json_response("success", result)
    except Exception as e:
        logger.error(f"Error in list_crash_dumps: {e}", exc_info=True)
        return _json_response("error", error=f"Error scanning for dumps: {str(e)}")


def start_session(vmcore_path: str, vmlinux_path: str, 
                  ssh_host: Optional[str] = None, ssh_user: Optional[str] = None,
                  crash_args: Optional[str] = None) -> str:
    """启动分析会话。"""
    # Parse crash_args
    args_list = crash_args.split(',') if crash_args else []
    
        # Validation
    if not ssh_host and not os.path.exists(vmcore_path):
        return _json_response("error", error=f"Dump file not found locally at {vmcore_path} and no remote host specified.")

    # Check version match
    version_warning = ""
    # Simplified validation for JSON response...
    # (Checking version logic kept but warning handling might change)
    if not ssh_host and os.path.exists(vmcore_path) and os.path.exists(vmlinux_path):
        match_result = CrashDiscovery.check_version_match(vmcore_path, vmlinux_path)
        if not match_result.get('match') and match_result.get('vmcore_version'):
            version_warning = match_result['message'] # Store warning text

    session_id = str(uuid.uuid4())
    logger.info(f"Starting Session {session_id} for {vmcore_path}")
    
    try:
        session = UnifiedSession(vmcore_path, vmlinux_path, 
                               remote_host=ssh_host, remote_user=ssh_user,
                               crash_args=args_list)
        session.start()
        
        context.sessions[session_id] = session
        context.last_session_id = session_id
        
        result = {"session_id": session_id}
        if version_warning:
            result["warning"] = version_warning
            
        return _json_response("success", result)
    except Exception as e:
        logger.error(f"Failed to start session: {e}")
        return _json_response("error", error=f"Failed to start session: {str(e)}")


def run_crash_command(command: str, session_id: Optional[str] = None, truncate: bool = True) -> str:
    """执行 crash 命令。"""
    target_id = session_id or context.last_session_id
    
    if not target_id:
        return _json_response("error", error="No session specified and no active default session.")
    
    if target_id not in context.sessions:
        return _json_response("error", error=f"Session ID {target_id} not found.")
    
    session = context.sessions[target_id]
    if not session.is_active():
        del context.sessions[target_id]
        return _json_response("error", error="Session is no longer active.")
        
    try:
        output = session.execute_command(f"crash:{command}", truncate=truncate)
        return _json_response("success", output)
    except Exception as e:
        return _json_response("error", error=str(e))


def run_drgn_command(command: str, session_id: Optional[str] = None, truncate: bool = True) -> str:
    """执行 drgn 代码。"""
    target_id = session_id or context.last_session_id
    
    if not target_id:
        return _json_response("error", error="No session specified and no active default session.")
    
    if target_id not in context.sessions:
        return _json_response("error", error=f"Session ID {target_id} not found.")
    
    session = context.sessions[target_id]
    if not session.is_active():
        del context.sessions[target_id]
        return _json_response("error", error="Session is no longer active.")
        
    try:
        output = session.execute_command(f"drgn:{command}", truncate=truncate)
        return _json_response("success", output)
    except Exception as e:
        return _json_response("error", error=str(e))


def run_pykdump_command(code: str, session_id: Optional[str] = None, truncate: bool = True) -> str:
    """执行 pykdump 代码。"""
    target_id = session_id or context.last_session_id
    
    if not target_id:
        return _json_response("error", error="No session specified and no active default session.")
    
    if target_id not in context.sessions:
        return _json_response("error", error=f"Session ID {target_id} not found.")
    
    session = context.sessions[target_id]
    if not session.is_active():
        del context.sessions[target_id]
        return _json_response("error", error="Session is no longer active.")
        
    try:
        output = session.execute_command(f"pykdump:{code}", truncate=truncate)
        return _json_response("success", output)
    except Exception as e:
        return _json_response("error", error=str(e))


def stop_session(session_id: Optional[str] = None) -> str:
    """终止会话。"""
    target_id = session_id or context.last_session_id
    
    if not target_id:
        return _json_response("error", error="No session specified and no active default session.")
    
    if target_id not in context.sessions:
        return _json_response("error", error=f"Session ID {target_id} not found.")
        
    session = context.sessions[target_id]
    session.stop()
    del context.sessions[target_id]
    
    if context.last_session_id == target_id:
        context.last_session_id = None
        
    return _json_response("success", "Session closed")


def get_sys_info(session_id: Optional[str] = None) -> str:
    """Convenience tool to get system info (runs 'sys' command)."""
    return run_crash_command("sys", session_id)


def register(mcp: FastMCP):
    """Register session management tools with MCP server."""
    mcp.tool()(list_crash_dumps)
    mcp.tool()(start_session)
    mcp.tool()(run_crash_command)
    mcp.tool()(run_drgn_command)
    mcp.tool()(run_pykdump_command)
    mcp.tool()(stop_session)
    # mcp.tool()(get_sys_info)  # Hidden: too simple, use run_crash_command("sys") instead
