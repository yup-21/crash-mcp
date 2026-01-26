"""Analysis Scripts Tool - Execute predefined drgn analysis scripts."""
import logging
from typing import Optional, Dict, Any
from mcp.server.fastmcp import FastMCP

from crash_mcp.tools.utils import json_response, get_session
from crash_mcp.resource.loader import (
    get_script_registry, 
    load_script,
    refresh_script_registry
)

logger = logging.getLogger("crash-mcp")


def _get_script_registry() -> Dict[str, Dict[str, Any]]:
    """
    Get script registry from auto-discovery.
    
    Scripts are discovered from resource/scripts/*.py with metadata from:
    1. YAML frontmatter in docstring
    2. Fallback to basic docstring parsing
    """
    return get_script_registry()


def _build_script_with_params(script_name: str, params: Optional[Dict[str, Any]]) -> str:
    """
    Build executable script by prepending parameter assignments.
    """
    script_content = load_script(script_name)
    
    if not params:
        return script_content
    
    # Build parameter injection lines
    param_lines = []
    for key, value in params.items():
        if isinstance(value, str):
            safe_value = value.replace("'", "\\'")
            param_lines.append(f"{key} = '{safe_value}'")
        elif isinstance(value, bool):
            param_lines.append(f"{key} = {value}")
        elif isinstance(value, (int, float)):
            param_lines.append(f"{key} = {value}")
        else:
            param_lines.append(f"{key} = {repr(value)}")
    
    if param_lines:
        prefix = "\n".join(param_lines) + "\n\n"
        return prefix + script_content
    
    return script_content


# =============================================================================
# MCP Tool Definitions
# =============================================================================

def run_analysis_script(
    script_name: str,
    params: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None
) -> str:
    """Run a predefined drgn analysis script.
    
    Use list_analysis_scripts() to see available scripts and parameters.
    """
    registry = _get_script_registry()
    
    # Validate script name
    if script_name not in registry:
        available = ", ".join(sorted(registry.keys()))
        return json_response("error", error=f"Unknown script: '{script_name}'. Available: {available}")
    
    # Get session
    try:
        target_id, session = get_session(session_id)
    except ValueError as e:
        return json_response("error", error=str(e))
    
    # Validate required parameters
    script_meta = registry[script_name]
    params = params or {}
    for param_name, param_info in script_meta.get("params", {}).items():
        if param_info.get("required") and param_name not in params:
            return json_response("error", error=f"Missing required parameter: '{param_name}' ({param_info.get('desc', '')})")
    
    try:
        # Build script with injected parameters
        full_script = _build_script_with_params(script_name, params)
        
        # Execute via drgn session
        output = session.execute_command(f"drgn:{full_script}", truncate=False)
        
        return json_response("success", {
            "script": script_name,
            "output": output,
            "session_id": target_id
        })
        
    except FileNotFoundError as e:
        return json_response("error", error=str(e))
    except Exception as e:
        logger.error(f"Error executing script '{script_name}': {e}")
        return json_response("error", error=f"Script execution failed: {e}")


def list_analysis_scripts(category: Optional[str] = None) -> str:
    """List available analysis scripts with descriptions and parameters.
    """
    registry = _get_script_registry()
    scripts_info = []
    
    for name, meta in sorted(registry.items()):
        script_category = meta.get('category', 'utility')
        if category and script_category != category:
            continue
            
        script_info = {
            "name": name,
            "description": meta.get("description", ""),
            "category": script_category,
            "params": {}
        }
        for param_name, param_info in meta.get("params", {}).items():
            if isinstance(param_info, dict):
                script_info["params"][param_name] = {
                    "type": param_info.get("type", "str"),
                    "description": param_info.get("desc", ""),
                    "required": param_info.get("required", False)
                }
        scripts_info.append(script_info)
    
    return json_response("success", {"scripts": scripts_info, "total": len(scripts_info)})


# =============================================================================
# Registration
# =============================================================================

def register(mcp: FastMCP):
    """Register analysis script tools with MCP server."""
    from crash_mcp.tools.tool_logging import logged_tool
    
    mcp.tool()(logged_tool(run_analysis_script))
    mcp.tool()(logged_tool(list_analysis_scripts))
