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


def _convert_param_for_injection(key: str, value: Any, expected_type: Optional[str] = None) -> str:
    """
    Convert a parameter value to its Python code representation.
    
    Intelligently handles type conversion based on:
    1. Explicit type hints from param metadata
    2. Value format detection (0x prefix -> int, numeric strings -> int)
    """
    # Already native types
    if isinstance(value, bool):
        return f"{key} = {value}"
    if isinstance(value, int):
        return f"{key} = {value}"
    if isinstance(value, float):
        return f"{key} = {value}"
    
    # String with type hint or format detection
    if isinstance(value, str):
        # Explicit int type expected from metadata
        if expected_type == "int":
            return f"{key} = int({repr(value)}, 0)"  # 0 = auto-detect base
        
        # Auto-detect hex format (0x or 0X prefix)
        if value.startswith("0x") or value.startswith("0X"):
            return f"{key} = int({repr(value)}, 16)"
        
        # Auto-detect decimal integer (including negative)
        if value.lstrip("-").isdigit() and value:
            return f"{key} = int({repr(value)})"
        
        # Default: keep as string
        safe_value = value.replace("'", "\\'")
        return f"{key} = '{safe_value}'"
    
    # Fallback for other types
    return f"{key} = {repr(value)}"


def _build_script_with_params(
    script_name: str, 
    params: Optional[Dict[str, Any]],
    param_meta: Optional[Dict[str, Dict[str, Any]]] = None
) -> str:
    """
    Build executable script by prepending parameter assignments.
    
    Intelligently handles type conversion based on param metadata and format detection.
    """
    script_content = load_script(script_name)
    
    if not params:
        return script_content
    
    param_meta = param_meta or {}
    
    # Build parameter injection lines with intelligent type conversion
    param_lines = []
    for key, value in params.items():
        expected_type = param_meta.get(key, {}).get("type")
        param_lines.append(_convert_param_for_injection(key, value, expected_type))
    
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
    injected_params = params.copy()
    
    for param_name, param_info in script_meta.get("params", {}).items():
        # 1. Check required
        if param_info.get("required") and param_name not in params:
            return json_response("error", error=f"Missing required parameter: '{param_name}' ({param_info.get('desc', '')})")
            
        # 2. Type Conversion (str -> int for hex/dec)
        if param_name in params:
            val = params[param_name]
            expected_type = param_info.get("type")
            
            if expected_type == "int" and isinstance(val, str):
                try:
                    # Auto-detect base (0x for hex)
                    injected_params[param_name] = int(val, 0)
                except ValueError:
                    return json_response("error", error=f"Invalid int value for '{param_name}': '{val}'")
    
    try:
        # Build script with injected parameters (pass param metadata for type hints)
        full_script = _build_script_with_params(script_name, injected_params, script_meta.get("params", {}))
        
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
    """Register analysis script tools with MCP server.
    
    Only registers if DRGN_SCRIPTS_PATH is configured.
    """
    from crash_mcp.config import Config
    from crash_mcp.tools.tool_logging import logged_tool
    
    if not Config.DRGN_SCRIPTS_PATH:
        logger.debug("Analysis script tools not registered (DRGN_SCRIPTS_PATH not set)")
        return
    
    logger.info(f"Registering analysis script tools (scripts: {Config.DRGN_SCRIPTS_PATH})")
    mcp.tool()(logged_tool(run_analysis_script))
    mcp.tool()(logged_tool(list_analysis_scripts))
