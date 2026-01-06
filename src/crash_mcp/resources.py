from mcp.server.fastmcp import FastMCP
from crash_mcp.prompts import get_system_prompt

def register(mcp: FastMCP):
    """Register resources with MCP server."""
    
    @mcp.resource("crash-mcp://system_prompt")
    def analysis_prompt_resource() -> str:
        """Get the full system prompt used for crash analysis."""
        return get_system_prompt()
