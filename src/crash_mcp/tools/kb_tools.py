"""Knowledge Base tools for crash-mcp."""
import os
import json
import logging
from typing import Optional
from mcp.server.fastmcp import FastMCP

from crash_mcp.config import Config
from crash_mcp.kb import get_layered_retriever

logger = logging.getLogger("crash-mcp")


def _get_kb_base_dir() -> str:
    """Get absolute path to KB base directory."""
    base = Config.KB_BASE_DIR
    if base and os.path.isabs(base):
        return base
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    return os.path.join(project_root, base) if base else project_root


def _get_methods_dir() -> str:
    return os.path.join(_get_kb_base_dir(), 'knowledge', 'methods')


def _get_data_dir() -> str:
    return os.path.join(_get_kb_base_dir(), 'data', 'chroma')


def kb_search_symptom(query: str) -> str:
    """[L1] Search Symptom Library (Vector+Keyword) for matching methods."""
    retriever = get_layered_retriever(_get_methods_dir(), _get_data_dir())
    results = retriever.search_symptom(query, top_k=3)
    
    if not results:
        return "No matching symptoms/methods found."
        
    output = []
    for r in results:
        output.append(f"## Protocol: {r['name']} (Score: {r['score']:.2f})")
        output.append(f"ID: {r['id']}")
        output.append(f"Source: {r.get('source', 'unknown')}")
        output.append("Steps:")
        for s in r['steps']:
            output.append(f"  - {s['command']}")
        output.append("")
    return "\n".join(output)


def kb_analyze_method(method_id: str) -> str:
    """[L2] Execute Analysis Method and return structured context.
    Returns JSON string with commands to run and expected outputs."""
    retriever = get_layered_retriever(_get_methods_dir(), _get_data_dir())
    method_data = retriever.analyze_method(method_id)
    return json.dumps(method_data, indent=2)


def kb_search_subproblem(query: str, context: str) -> str:
    """[L3] Search for sub-problems based on context. 
    Context should be a JSON string of findings."""
    try:
        ctx_dict = json.loads(context)
    except:
        ctx_dict = {"raw": context}
        
    retriever = get_layered_retriever(_get_methods_dir(), _get_data_dir())
    hits = retriever.search_subproblem(query, ctx_dict)
    
    if not hits:
        return "No known sub-problems found."
        
    return json.dumps(hits, indent=2)


def kb_match_or_save_node(fingerprint: str, data: str) -> str:
    """[L3] Match existing Case Node or save new one.
    Data should be JSON string."""
    try:
        data_dict = json.loads(data)
    except:
        return "Error: Data must be valid JSON"
        
    retriever = get_layered_retriever(_get_methods_dir(), _get_data_dir())
    node_id = retriever.match_or_save_node(fingerprint, data_dict)
    return f"Node Ref: {node_id}"


def kb_run_workflow(panic_text: str, session_id: Optional[str] = None) -> str:
    """[Workflow] Start/Continue analysis workflow. 
    Stateful orchestration of the analysis loop."""
    from crash_mcp.kb.workflow import quick_start
    
    res = quick_start(panic_text, methods_dir=_get_methods_dir())
    return json.dumps(res, indent=2)


def kb_mark_node_failed(node_id: str) -> str:
    """[L3] Mark a case node as failed/dead-end for negative feedback."""
    retriever = get_layered_retriever(_get_methods_dir(), _get_data_dir())
    success = retriever.mark_node_failed(node_id)
    if success:
        return f"Node {node_id} marked as failed."
    return f"Error: Node {node_id} not found."


def kb_list_scripts(category: Optional[str] = None) -> str:
    """[Utility] List available drgn scripts with usage info.
    
    Args:
        category: Optional filter - 'analysis', 'lock', 'memory', 'utility', or None for all.
    
    Returns:
        Formatted list of scripts with descriptions and usage examples.
    """
    scripts_dir = os.path.join(_get_kb_base_dir(), 'knowledge', 'scripts', 'drgn')
    
    # Script metadata
    script_info = {
        # Analysis scripts (covered by methods)
        'lock_mutex': {'category': 'lock', 'desc': 'Mutex 锁分析', 'params': 'lock_addr'},
        'lock_rwsem': {'category': 'lock', 'desc': 'RW Semaphore 分析', 'params': 'lock_addr'},
        'lock_spinlock': {'category': 'lock', 'desc': 'Spinlock 分析 (含锁依赖检测)', 'params': 'lock_addr'},
        'hung_task': {'category': 'analysis', 'desc': 'D 状态任务分析', 'params': None},
        'panic_info': {'category': 'analysis', 'desc': 'Panic 信息提取', 'params': None},
        'slab_dump': {'category': 'memory', 'desc': 'Slab 内存分析', 'params': None},
        'stack_trace': {'category': 'analysis', 'desc': '调用栈分析', 'params': 'pid'},
        'memory': {'category': 'memory', 'desc': '内存使用统计', 'params': None},
        'task_list': {'category': 'analysis', 'desc': '任务列表过滤', 'params': 'state_char, comm_filter'},
        # Utility scripts
        'address_detect': {'category': 'utility', 'desc': '地址类型检测 (符号/Slab)', 'params': 'addr'},
        'cpu_irq_stack': {'category': 'utility', 'desc': 'CPU IRQ 栈分析', 'params': 'target_cpu'},
        'list_traversal': {'category': 'utility', 'desc': '内核链表遍历', 'params': 'root_val, target_type, member_name'},
        'rbtree_traversal': {'category': 'utility', 'desc': '红黑树遍历', 'params': 'root_val, target_type, member_name'},
        'struct_inspect': {'category': 'utility', 'desc': '结构体递归打印', 'params': 'struct_type, address, depth'},
    }
    
    # List actual files
    available = []
    try:
        for f in os.listdir(scripts_dir):
            if f.endswith('.py') and f != '__init__.py':
                name = f[:-3]
                info = script_info.get(name, {'category': 'other', 'desc': '(无描述)', 'params': None})
                if category is None or info['category'] == category:
                    available.append({'name': name, **info})
    except Exception as e:
        return f"Error listing scripts: {e}"
    
    if not available:
        return f"No scripts found for category: {category}"
    
    # Format output
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
        lines.append("")
        for s in sorted(scripts, key=lambda x: x['name']):
            params_str = f" ({s['params']})" if s['params'] else ""
            lines.append(f"- **{s['name']}**{params_str}: {s['desc']}")
        lines.append("")
    
    lines.append("---")
    lines.append("**Usage Example:**")
    lines.append("```python")
    lines.append("# Via run_drgn_command:")
    lines.append("run_drgn_command('lock_addr=0xffff...; exec(open(\"/path/to/lock_spinlock.py\").read())')")
    lines.append("")
    lines.append("# Or use kb_analyze_method for structured guidance:")
    lines.append("kb_analyze_method('spinlock_analysis')")
    lines.append("```")
    
    return "\n".join(lines)


def _get_scripts_dir() -> str:
    """Get absolute path to scripts directory."""
    return os.path.join(_get_kb_base_dir(), 'knowledge', 'scripts', 'drgn')


def kb_get_script(script_name: str) -> str:
    """[Utility] Get the content of a drgn script by name.
    
    Args:
        script_name: Script name without .py extension.
    
    Returns:
        Script content or error message.
    """
    scripts_dir = _get_scripts_dir()
    path = os.path.join(scripts_dir, f"{script_name}.py")
    
    if not os.path.exists(path):
        available = kb_list_scripts()
        return f"Error: Script '{script_name}' not found.\n\n{available}"
    
    with open(path, 'r') as f:
        content = f.read()
    
    return f"## Script: {script_name}.py\n\n```python\n{content}\n```"


def register(mcp: FastMCP):
    """Register Knowledge Base tools with MCP server."""
    mcp.tool()(kb_search_symptom)
    mcp.tool()(kb_analyze_method)
    mcp.tool()(kb_search_subproblem)
    mcp.tool()(kb_match_or_save_node)
    mcp.tool()(kb_run_workflow)
    mcp.tool()(kb_mark_node_failed)
    mcp.tool()(kb_list_scripts)
    mcp.tool()(kb_get_script)

