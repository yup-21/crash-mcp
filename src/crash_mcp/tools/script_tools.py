"""Script Library tools for crash-mcp.

Provides script management capabilities:
- Listing available scripts (dynamic discovery via docstrings)
- Reading script details and source code
- Saving new scripts for review
"""
import os
import logging
import datetime
from typing import Optional
from mcp.server.fastmcp import FastMCP
from crash_mcp.resource import loader

logger = logging.getLogger("crash-mcp")

# ==============================================================================
# MCP Tools
# ==============================================================================

def list_scripts(category: Optional[str] = None) -> str:
    """[Utility] 列出可用的 drgn 分析脚本。
    
    动态扫描资源目录，解析脚本头部的文档注释。
    
    参数:
        category: 可选过滤 - 'lock', 'memory', 'net', 'analysis', 'utility'。
    
    返回:
        格式化的脚本列表及功能摘要。
    """
    available = loader.list_available_scripts(category)
    
    if not available:
        return f"No scripts found" + (f" for category: {category}" if category else "")
    
    # Format Output
    lines = [f"## Available Drgn Scripts ({len(available)})", ""]
    
    # Group by category
    categories = {}
    for s in available:
        cat = s['category']
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(s)
    
    for cat, scripts in sorted(categories.items()):
        lines.append(f"### {cat.upper()}")
        for s in sorted(scripts, key=lambda x: x['name']):
            usage = f" (Usage: {s['params']})" if s['params'] else ""
            lines.append(f"- **{s['name']}**: {s['desc']}{usage}")
        lines.append("")
    
    lines.append("---")
    lines.append("**Tip**: Use `read_script('name')` to see full docs.")
    lines.append("Use `run_drgn_command('param=...; script.py')` to execute.")
    return "\n".join(lines)


def read_script(script_name: str, show_code: bool = False) -> str:
    """[Utility] 读取 drgn 脚本内容或说明。
    
    参数:
        script_name: 脚本名称 (不含 .py 扩展名)。
        show_code: 如果为 True，返回完整源代码；默认 False (仅返回使用说明)。
    """
    try:
        # Check existence via loader logic
        path = os.path.join(loader.get_scripts_dir(), f"{script_name}.py")
        if not os.path.exists(path):
            return f"Error: Script '{script_name}' not found."
            
        info_str = f"## Script: {script_name}.py\n"
        info_str += f"**Path**: `{path}`\n\n"
        
        if not show_code:
            info_str += "**Usage (via run_drgn_command)**:\n"
            info_str += "```python\n"
            info_str += f"# 1. Set parameters\n"
            info_str += f"# 2. Run script\n"
            info_str += f"run_drgn_command(\"<params>=...; {script_name}.py\")\n"
            info_str += "```\n\n"
            info_str += f"> **Note**: To view full source code, call `read_script('{script_name}', show_code=True)`."
            return info_str
        
        content = loader.get_script_content(script_name)
        return f"{info_str}**Source Code**:\n```python\n{content}\n```"
    except Exception as e:
        return f"Error reading script: {e}"


def save_script(name: str, content: str) -> str:
    """[Write] 保存新脚本到待审核区。
    
    参数:
        name: 脚本名称 (不含 .py 扩展名)。
        content: 完整的 Python 脚本代码。
    """
    # Sanitize name
    safe_name = "".join(c for c in name if c.isalnum() or c in ('_', '-'))
    if not safe_name:
        return "Error: Invalid name. Use alphanumeric characters, underscores, or hyphens."
    
    try:
        # Build path: src/crash_mcp/resource/scripts/pending
        pending_dir = loader.get_pending_scripts_dir()
        os.makedirs(pending_dir, exist_ok=True)
        
        # Add timestamp
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{safe_name}_{timestamp}.py"
        filepath = os.path.join(pending_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # Guide user to the new resource location for approval
        approve_path = os.path.join("src", "crash_mcp", "resource", "scripts", "drgn", f"{safe_name}.py")
        return f"✅ Script saved to pending review: {filepath}\n\nTo approve, move to: {approve_path}"
    except Exception as e:
        logger.error(f"Failed to save pending script: {e}")
        return f"Error saving script: {e}"


def register(mcp: FastMCP):
    """Register Script Library tools with MCP server."""
    mcp.tool()(list_scripts)
    mcp.tool()(read_script)
    mcp.tool()(save_script)
