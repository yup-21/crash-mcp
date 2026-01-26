"""
Script loading and auto-discovery utilities.

Supports:
1. YAML frontmatter in script docstrings
2. External scripts.yaml configuration  
3. Fallback to basic docstring parsing
"""
import os
import re
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger("crash-mcp")

# =============================================================================
# Path Utilities
# =============================================================================

def get_scripts_dirs() -> List[str]:
    """
    Get list of script directories to search.
    
    Priority:
    1. DRGN_SCRIPTS_PATH environment variable (colon-separated)
    2. Built-in resource/scripts (fallback, if exists)
    """
    from crash_mcp.config import Config
    
    dirs = []
    
    # 1. External paths from env
    if Config.DRGN_SCRIPTS_PATH:
        for p in Config.DRGN_SCRIPTS_PATH.split(":"):
            p = p.strip()
            if p and os.path.isdir(p):
                dirs.append(p)
    
    # 2. Built-in fallback (only if no external paths configured)
    if not dirs:
        current = os.path.dirname(os.path.abspath(__file__))
        builtin = os.path.join(current, 'scripts')
        if os.path.isdir(builtin):
            dirs.append(builtin)
    
    return dirs


def get_scripts_config_path() -> str:
    """Get path to optional scripts.yaml config file (in resource/ directory)."""
    current = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(current, 'scripts.yaml')


# =============================================================================
# Frontmatter Parsing
# =============================================================================

def parse_yaml_frontmatter(content: str) -> Optional[Dict[str, Any]]:
    """
    Parse YAML frontmatter from script content.
    
    Expects format:
    '''
    ---
    description: What it does
    params:
      param1:
        type: int
        desc: Description
        required: true
    ---
    Actual docstring...
    '''
    """
    # Match docstring with YAML frontmatter
    # Pattern: optional shebang, then """ or ''' followed by newline, ---, yaml content, ---, rest
    pattern = r'^(?:#!.*\n)?["\']{{3}}\s*\n---\s*\n(.*?)\n---\s*\n'.replace('{{3}}', '{3}')
    match = re.match(pattern, content, re.DOTALL)
    
    if not match:
        return None
    
    yaml_content = match.group(1)
    
    try:
        import yaml
        return yaml.safe_load(yaml_content)
    except ImportError:
        # Fallback: simple YAML-like parsing for basic cases
        return _parse_simple_yaml(yaml_content)
    except Exception as e:
        logger.warning(f"Failed to parse YAML frontmatter: {e}")
        return None


def _parse_simple_yaml(content: str) -> Dict[str, Any]:
    """Simple YAML parser for basic key-value pairs (fallback without PyYAML)."""
    result = {}
    current_key = None
    current_indent = 0
    
    for line in content.splitlines():
        if not line.strip():
            continue
            
        # Count leading spaces
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()
        
        if ':' in stripped:
            key, _, value = stripped.partition(':')
            key = key.strip()
            value = value.strip()
            
            if value:
                # Simple key: value
                if indent == 0:
                    result[key] = value
            else:
                # Nested structure - skip for simple parser
                if indent == 0:
                    result[key] = {}
                    current_key = key
                    current_indent = indent
    
    return result


def parse_docstring_fallback(content: str) -> Dict[str, Any]:
    """
    Fallback parser: extract description from first docstring line.
    """
    import ast
    result = {"description": "(No description)", "params": {}}
    
    try:
        module = ast.parse(content)
        docstring = ast.get_docstring(module)
        
        if docstring:
            lines = [l.strip() for l in docstring.splitlines() if l.strip()]
            
            # Skip YAML frontmatter markers if present
            if lines and lines[0] == '---':
                # Find end of frontmatter
                try:
                    end_idx = lines.index('---', 1)
                    lines = lines[end_idx + 1:]
                except ValueError:
                    pass
            
            if lines:
                result["description"] = lines[0]
                
            # Try to extract params from "用法:" or "Usage:" line
            for line in lines:
                if "用法:" in line or "Usage:" in line:
                    parts = line.split(":", 1)
                    if len(parts) > 1:
                        result["usage"] = parts[1].strip()
                    break
    except Exception:
        pass
        
    return result


# =============================================================================
# Script Discovery
# =============================================================================

def load_external_config() -> Dict[str, Dict[str, Any]]:
    """Load scripts.yaml if present."""
    config_path = get_scripts_config_path()
    
    if not os.path.exists(config_path):
        return {}
    
    try:
        import yaml
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        if config and isinstance(config.get('scripts'), dict):
            return config['scripts']
        return {}
    except ImportError:
        logger.warning("PyYAML not installed, skipping scripts.yaml")
        return {}
    except Exception as e:
        logger.warning(f"Failed to load scripts.yaml: {e}")
        return {}


def discover_scripts() -> Dict[str, Dict[str, Any]]:
    """
    Auto-discover all scripts with metadata from configured directories.
    
    Priority:
    1. scripts.yaml (external config)
    2. YAML frontmatter in script
    3. Docstring fallback
    
    Returns:
        Dict mapping script_name -> metadata
    """
    scripts_dirs = get_scripts_dirs()
    registry = {}
    
    if not scripts_dirs:
        logger.debug("No script directories configured (set DRGN_SCRIPTS_PATH)")
        return registry
    
    # Load external config first
    external_config = load_external_config()
    
    # Scan all configured directories
    for scripts_dir in scripts_dirs:
        for filename in sorted(os.listdir(scripts_dir)):
            if not filename.endswith('.py') or filename.startswith('_'):
                continue
                
            script_name = filename[:-3]  # Remove .py
            
            # Skip if already discovered (first path wins)
            if script_name in registry:
                continue
                
            script_path = os.path.join(scripts_dir, filename)
            
            try:
                with open(script_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception as e:
                logger.warning(f"Failed to read {filename}: {e}")
                continue
            
            # Priority 1: External config
            if script_name in external_config:
                meta = external_config[script_name].copy()
                meta.setdefault('file', script_path)
                meta['params'] = _normalize_params(meta.get('params', {}))
                registry[script_name] = meta
                continue
            
            # Priority 2: YAML frontmatter
            frontmatter = parse_yaml_frontmatter(content)
            if frontmatter:
                meta = {
                    'description': frontmatter.get('description', ''),
                    'params': _normalize_params(frontmatter.get('params', {})),
                    'file': script_path,
                    'category': frontmatter.get('category', _categorize_script(script_name))
                }
                registry[script_name] = meta
                continue
            
            # Priority 3: Docstring fallback
            fallback = parse_docstring_fallback(content)
            registry[script_name] = {
                'description': fallback.get('description', ''),
                'params': {},  # Cannot extract params from basic docstring
                'file': script_path,
                'category': _categorize_script(script_name)
            }
    
    return registry


def _normalize_params(params: Any) -> Dict[str, Dict[str, Any]]:
    """Normalize params to standard format."""
    if not params or not isinstance(params, dict):
        return {}
        
    normalized = {}
    for name, info in params.items():
        if isinstance(info, dict):
            normalized[name] = {
                'type': info.get('type', 'str'),
                'desc': info.get('desc', info.get('description', '')),
                'required': info.get('required', False)
            }
        else:
            # Simple string description
            normalized[name] = {
                'type': 'str',
                'desc': str(info),
                'required': False
            }
    return normalized


def _categorize_script(name: str) -> str:
    """Heuristic categorization based on script name."""
    if name.startswith('lock_'):
        return 'lock'
    if name.startswith('net_'):
        return 'network'
    if name in ['memory', 'slab_dump', 'leak_scan']:
        return 'memory'
    if name in ['stack_trace', 'panic_info', 'hung_task', 'task_list', 'cpu_irq_stack']:
        return 'analysis'
    if name in ['struct_inspect', 'address_detect', 'list_traversal', 'rbtree_traversal']:
        return 'inspection'
    return 'utility'


# =============================================================================
# Script Loading
# =============================================================================

def load_script(script_name: str) -> str:
    """Load script content by name."""
    registry = get_script_registry()
    
    if script_name not in registry:
        raise FileNotFoundError(f"Script '{script_name}' not found in registry")
        
    path = registry[script_name].get('file')
    if not path or not os.path.exists(path):
        raise FileNotFoundError(f"Script file for '{script_name}' not found at {path}")
    
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def get_script_registry() -> Dict[str, Dict[str, Any]]:
    """Get the complete script registry (cached on first call)."""
    if not hasattr(get_script_registry, '_cache'):
        get_script_registry._cache = discover_scripts()
        logger.info(f"Discovered {len(get_script_registry._cache)} analysis scripts")
    return get_script_registry._cache


def refresh_script_registry() -> Dict[str, Dict[str, Any]]:
    """Force refresh the script registry."""
    if hasattr(get_script_registry, '_cache'):
        del get_script_registry._cache
    return get_script_registry()
