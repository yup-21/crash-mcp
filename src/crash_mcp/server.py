"""Crash MCP Server - Main entry point."""
import logging
import click
from mcp.server.fastmcp import FastMCP

from crash_mcp.config import Config

# Configure logging
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL.upper()), 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("server.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("crash-mcp")


def register_all_tools(mcp: FastMCP):
    """
    注册所有 MCP 工具。
    
    工具分组:
    - Session Management (6个): list_crash_dumps, start_session, stop_session, 
                                run_crash_command, run_drgn_command, get_sys_info
    - Knowledge Base (5个): kb_recommend_method, kb_get_method_guide, kb_find_similar_findings,
                           kb_record_finding, kb_quick_start
    """
    from crash_mcp.tools import session_mgmt
    session_mgmt.register(mcp)
    
    from crash_mcp.tools import kb_tools
    kb_tools.register(mcp)

    from crash_mcp import prompts
    prompts.register(mcp)

    from crash_mcp import resources
    resources.register(mcp)


def create_mcp_server() -> FastMCP:
    """Create and configure MCP server."""
    from crash_mcp.prompts import get_system_prompt
    
    mcp = FastMCP(
        name="crash-mcp",
        instructions=get_system_prompt()  # Auto-inject system prompt to clients
    )
    register_all_tools(mcp)
    return mcp


# Create global mcp instance for module-level access
mcp = create_mcp_server()


def main():
    """Entry point for console script."""
    cli()


@click.command()
@click.option('--transport', type=click.Choice(['stdio', 'sse']), default='stdio', help='Transport mode')
@click.option('--port', type=int, default=8000, help='Port for SSE mode')
@click.option('--host', default='0.0.0.0', help='Host for SSE mode')
def cli(transport, port, host):
    """Start the Crash MCP server."""
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
