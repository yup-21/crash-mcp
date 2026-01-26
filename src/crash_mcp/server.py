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
    - Session Management: list_crash_dumps, open_vmcore_session, close_crash_session, 
                          run_crash_command, run_drgn_command, run_pykdump_command
    - Output Tools: get_command_output, search_command_output
    """
    from crash_mcp.tools import session_mgmt
    session_mgmt.register(mcp)
    
    from crash_mcp.tools import output_tools
    output_tools.register(mcp)
    
    from crash_mcp.tools import analysis_scripts
    analysis_scripts.register(mcp)

    from crash_mcp.tools import get_info
    get_info.register(mcp)

    # Prompts
    from crash_mcp import prompts
    prompts.register(mcp)


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
        
        # Disable strict host checking to allow external access (e.g. 172.x.x.x)
        # This fixes "HTTP 421 Misdirected Request / Invalid Host header"
        if hasattr(mcp.settings, 'transport_security') and mcp.settings.transport_security:
            # Completely disable strict host checking
            mcp.settings.transport_security.enable_dns_rebinding_protection = False
            mcp.settings.transport_security.allowed_hosts = ["*"]
            mcp.settings.transport_security.allowed_origins = ["*"]
        
        mcp.run(transport='sse')
    else:
        logger.info("Starting Stdio server")
        mcp.run(transport='stdio')


if __name__ == "__main__":
    cli()
