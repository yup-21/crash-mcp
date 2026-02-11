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
    
    The timeout has a minimum value of 300 seconds to support large dump analysis.
    """
    cmd_template = Config.GET_DUMPINFO_SCRIPT
    # Enforce minimum timeout of 300s for stability to handle large dumps
    if timeout < 300:
        logger.info(f"Overriding timeout {timeout}s -> 300s (minimum)")
        timeout = 300

    if not cmd_template:
        return json_response("error", error="GET_DUMPINFO_SCRIPT not configured")
    
    # Get session for vmcore/vmlinux paths
    try:
        target_id, session = get_session(session_id)
    except ValueError as e:
        return json_response("error", error=str(e))
    
    # Get session for vmcore/vmlinux paths
    vmcore_path = getattr(session, 'dump_path', '')
    vmlinux_path = getattr(session, 'kernel_path', '')
    
    cmd_str = cmd_template.format(
        vmcore=vmcore_path,
        vmlinux=vmlinux_path
    )
    
    cmd_name = "get_crash_info"
    
    # Check cache first
    if session and session.command_store:
        cached = session.command_store.get_cached("script", cmd_name, {})
        if cached:
            if cached.output_file and cached.output_file.exists():
                try:
                    output = cached.output_file.read_text()
                    findings = _parse_report(output)
                    
                    if findings and "parse_error" not in findings:
                        logger.info(f"Cache hit for {cmd_name}")
                        return json_response("success", {
                            "findings": findings,
                            "cached": True
                        })
                except Exception as e:
                    logger.warning(f"Failed to read/parse cache for {cmd_name}: {e}")

    logger.info(f"Executing: {cmd_str}")
    
    try:
        result = subprocess.run(
            cmd_str,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout + 60
        )
        
        output = result.stdout
        findings = _parse_report(output)
            
        # Manually persist the full report to CommandStore
        if session and session.command_store:
            # Save raw output (stdout)
            session.command_store.save("script", cmd_name, result.stdout, {}, is_error=result.returncode != 0, force_save=True)
        
        return json_response("success", {
            "findings": findings,
            "stderr": result.stderr[-500:] if result.returncode != 0 and result.stderr else None
        })
        
    except subprocess.TimeoutExpired:
        return json_response("error", error=f"Script execution timed out ({timeout}s)")
    except Exception as e:
        logger.error(f"Error executing script: {e}")
        return json_response("error", error=str(e))


def _parse_report(output: str) -> dict:
    """Parse automated crash report JSON from output."""
    if "--- JSON REPORT START ---" in output:
        try:
            start = output.index("--- JSON REPORT START ---") + len("--- JSON REPORT START ---")
            end = output.index("--- JSON REPORT END ---")
            json_str = output[start:end].strip()
            return json.loads(json_str)
        except (ValueError, json.JSONDecodeError, IndexError) as e:
            logger.warning(f"Failed to parse JSON report: {e}")
            return {"parse_error": str(e), "raw_output": output[-2000:]}
    else:
        # No JSON markers, return raw output (truncated)
        return {"raw_output": output[-2000:] if len(output) > 2000 else output}


def register(mcp: FastMCP):
    """Conditionally register get_crash_info tool based on env config."""
    from crash_mcp.tools.tool_logging import logged_tool
    
    # Only expose tool if script command is configured
    if Config.GET_DUMPINFO_SCRIPT:
        logger.info(f"Registering get_crash_info tool (cmd: {Config.GET_DUMPINFO_SCRIPT})")
        mcp.tool()(logged_tool(get_crash_info))
    else:
        logger.debug("get_crash_info tool not registered (GET_DUMPINFO_SCRIPT not set)")
