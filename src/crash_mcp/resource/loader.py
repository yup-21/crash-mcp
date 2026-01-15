"""Script loading and parsing utilities."""
import os
import ast
from typing import Dict, List, Optional

def get_project_root() -> str:
    """Get the absolute path to the project root directory."""
    # src/crash_mcp/resource/loader.py -> src/crash_mcp/resource -> src/crash_mcp -> src -> project_root
    current = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(current, '..', '..', '..'))

def get_scripts_dir() -> str:
    """Get absolute path to scripts directory in resources."""
    # src/crash_mcp/resource/loader.py -> src/crash_mcp/resource -> ...
    current = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(current, 'scripts', 'drgn'))

def get_pending_scripts_dir() -> str:
    """Get absolute path to pending scripts directory."""
    return os.path.join(os.path.dirname(get_scripts_dir()), 'pending')

def parse_script_metadata(filepath: str) -> Dict[str, str]:
    """Parse script docstring to extract metadata (desc, params)."""
    meta = {"desc": "(No description)", "params": ""}
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            
        module = ast.parse(content)
        docstring = ast.get_docstring(module)
        
        if docstring:
            lines = [l.strip() for l in docstring.splitlines() if l.strip()]
            if lines:
                meta["desc"] = lines[0]
                
            # Extract usage/params
            for line in lines:
                if "Usage:" in line or "用法:" in line:
                    parts = line.split(":", 1)
                    if len(parts) > 1:
                        meta["params"] = parts[1].strip()
                    break
    except Exception as e:
        meta["desc"] = f"(Error parsing: {e})"
        
    return meta

def categorize_script(name: str) -> str:
    """Heuristic categorization based on script name."""
    if name.startswith('lock_'): return 'lock'
    if name.startswith('net_'): return 'net'
    if name in ['memory', 'slab_dump', 'leak_scan']: return 'memory'
    if name in ['stack_trace', 'panic_info', 'hung_task', 'task_list']: return 'analysis'
    return 'utility'

def list_available_scripts(category: Optional[str] = None) -> List[Dict[str, str]]:
    """List all available scripts with metadata."""
    scripts_dir = get_scripts_dir()
    if not os.path.exists(scripts_dir):
         return []
         
    available = []
    try:
        for f in sorted(os.listdir(scripts_dir)):
            if f.endswith('.py') and f != '__init__.py':
                name = f[:-3]
                path = os.path.join(scripts_dir, f)
                
                meta = parse_script_metadata(path)
                cat = categorize_script(name)
                
                if category is None or cat == category:
                    available.append({
                        'name': name,
                        'category': cat,
                        'desc': meta['desc'],
                        'params': meta['params'],
                        'path': path
                    })
    except Exception:
        pass
        
    return available

def get_script_content(name: str) -> str:
    """Get content of a script."""
    path = os.path.join(get_scripts_dir(), f"{name}.py")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Script {name} not found")
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()
