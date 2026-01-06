"""Drgn analysis scripts for crash-mcp.

这些脚本用于 Drgn 会话中执行深度分析。
Usage:
    from crash_mcp.kb.scripts import get_script
    script = get_script('rwsem')
    drgn_session.run_script(script)
"""
import os

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))

def get_script(name: str) -> str:
    """Load a script by name (without .py extension)."""
    path = os.path.join(SCRIPTS_DIR, f"{name}.py")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Script '{name}' not found at {path}")
    with open(path, 'r') as f:
        return f.read()

def list_scripts() -> list:
    """List all available scripts."""
    scripts = []
    for f in os.listdir(SCRIPTS_DIR):
        if f.endswith('.py') and f != '__init__.py':
            scripts.append(f[:-3])
    return sorted(scripts)
