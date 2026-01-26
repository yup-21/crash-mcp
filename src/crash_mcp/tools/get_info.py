"""Crash Info Tool - Get pre-diagnosis information via external script."""
import logging
import subprocess
import json
from typing import Optional
from mcp.server.fastmcp import FastMCP

from crash_mcp.config import Config
from crash_mcp.tools.utils import json_response, get_session

logger = logging.getLogger("crash-mcp")


def get_crash_info(session_id: Optional[str] = None, timeout: int = 300) -> str:
    """Get automated crash diagnosis report.
    """
    cmd_template = Config.GET_DUMPINFO_SCRIPT
    if not cmd_template:
        return json_response("error", error="GET_DUMPINFO_SCRIPT not configured")
    
    # Get session for vmcore/vmlinux paths
    try:
        target_id, session = get_session(session_id)
    except ValueError as e:
        return json_response("error", error=str(e))
    
    # Replace placeholders with session paths
    vmcore_path = getattr(session, 'vmcore_path', '')
    vmlinux_path = getattr(session, 'vmlinux_path', '')
    
    cmd_str = cmd_template.format(
        vmcore=vmcore_path,
        vmlinux=vmlinux_path
    )
    
    logger.info(f"Executing: {cmd_str}")
    
    try:
        result = subprocess.run(
            cmd_str,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout + 60
        )
        
        # Extract JSON from output (between markers)
        output = result.stdout
        findings = None
        
        if "--- JSON REPORT START ---" in output:
            try:
                start = output.index("--- JSON REPORT START ---") + len("--- JSON REPORT START ---")
                end = output.index("--- JSON REPORT END ---")
                json_str = output[start:end].strip()
                findings = json.loads(json_str)
            except (ValueError, json.JSONDecodeError) as e:
                logger.warning(f"Failed to parse JSON report: {e}")
                findings = {"parse_error": str(e), "raw_output": output[-2000:]}
        else:
            # No JSON markers, return raw output (truncated)
            findings = {"raw_output": output[-2000:] if len(output) > 2000 else output}
        
        return json_response("success", {
            "findings": findings,
            "stderr": result.stderr[-500:] if result.returncode != 0 and result.stderr else None
        })
        
    except subprocess.TimeoutExpired:
        return json_response("error", error=f"Script execution timed out ({timeout}s)")
    except Exception as e:
        logger.error(f"Error executing script: {e}")
        return json_response("error", error=str(e))


def register(mcp: FastMCP):
    """Conditionally register get_crash_info tool based on env config."""
    from crash_mcp.tools.tool_logging import logged_tool
    
    # Only expose tool if script command is configured
    if Config.GET_DUMPINFO_SCRIPT:
        logger.info(f"Registering get_crash_info tool (cmd: {Config.GET_DUMPINFO_SCRIPT})")
        mcp.tool()(logged_tool(get_crash_info))
    else:
        logger.debug("get_crash_info tool not registered (GET_DUMPINFO_SCRIPT not set)")
