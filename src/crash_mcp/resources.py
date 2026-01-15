from mcp.server.fastmcp import FastMCP
from crash_mcp.prompts import get_system_prompt
from crash_mcp.resource import loader

def register(mcp: FastMCP):
    """Register resources with MCP server.
    
    Note: Resources are hidden by default. 
    Use list_scripts/read_script tools instead.
    Skills provide detailed usage guidance.
    """
    
    # System prompt resource (hidden from default listing)
    # @mcp.resource("crash-mcp://system_prompt")
    # def analysis_prompt_resource() -> str:
    #     """Get the full system prompt used for crash analysis."""
    #     return get_system_prompt()
    
    # Script resources are hidden - use list_scripts/read_script tools instead
    # This reduces context pollution and supports progressive disclosure via Skills
    pass

