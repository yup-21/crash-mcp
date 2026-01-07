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



def kb_recommend_method(query: str) -> str:
    """[L1] 根据症状推荐分析方法。
    
    当看到崩溃症状时优先调用此工具。
    返回: 推荐的分析方法列表 (含 ID 和匹配度)。
    """
    retriever = get_layered_retriever(_get_methods_dir(), _get_data_dir())
    results = retriever.search_symptom(query, top_k=3)
    
    if not results:
        return "No matching symptoms/methods found."
        
    output = []
    for r in results:
        output.append(f"## Protocol: {r['name']} (Score: {r['score']:.2f})")
        output.append(f"ID: {r['id']}")
        output.append(f"Source: {r.get('source', 'unknown')}")
        output.append("Steps Preview:")
        for s in r['steps']:
            output.append(f"  - {s['command']}")
        output.append("")
    return "\n".join(output)


def kb_get_method_guide(method_id: str, include_next: bool = False) -> str:
    """[L2] 获取分析方法的详细步骤指南。
    
    在从 `kb_recommend_method` 选择方法 ID 后调用此工具。
    参数:
        method_id: 要获取的方法 ID。
        include_next: 如果为 True，返回结果中包含后续方法建议。
    返回: JSON 格式的执行步骤。
    """
    retriever = get_layered_retriever(_get_methods_dir(), _get_data_dir())
    method_data = retriever.analyze_method(method_id, include_next=include_next)
    return json.dumps(method_data, indent=2)


def kb_search_history(query: str, context: str = "{}") -> str:
    """[L3] 搜索历史案例/发现。
    
    用于检查是否遇到过类似问题。
    参数:
        query: 当前发现或症状的描述。
        context: 可选的上下文变量 (JSON 字符串)。
    """
    try:
        ctx_dict = json.loads(context)
    except:
        ctx_dict = {"raw": context}
        
    retriever = get_layered_retriever(_get_methods_dir(), _get_data_dir())
    hits = retriever.search_subproblem(query, ctx_dict)
    
    if not hits:
        return "No similar historical findings found."
        
    return json.dumps(hits, indent=2)


def kb_record_finding(fingerprint: str, data: str) -> str:
    """[L3] Record a key finding into the Knowledge Base.
    
    Use this to save valid findings or match existing ones (upsert).
    Args:
        fingerprint: Unique string ID for this type of issue.
        data: JSON string with finding details.
    """
    try:
        data_dict = json.loads(data)
    except:
        return "Error: Data must be valid JSON"
        
    retriever = get_layered_retriever(_get_methods_dir(), _get_data_dir())
    node_id = retriever.match_or_save_node(fingerprint, data_dict)
    return f"Node Ref: {node_id}"


def kb_quick_start(panic_text: str, session_id: Optional[str] = None) -> str:
    """[Workflow] 快速启动：自动选择最佳方法并返回命令。
    
    当你信任系统选择时使用此工具，实现"一键启动"。
    返回: JSON 格式，包含 method_id 和可执行的 commands。
    """
    from crash_mcp.kb.workflow import quick_start
    
    res = quick_start(panic_text, methods_dir=_get_methods_dir())
    return json.dumps(res, indent=2)


def kb_save_pending(asset_type: str, name: str, content: str) -> str:
    """[Write] 保存新知识资产到待审核区。
    
    用于保存分析过程中发现的新方法、案例或脚本。
    资产保存到 'knowledge/pending/'，需人工审核后移至正式目录。
    
    参数:
        asset_type: 'method'、'case' 或 'script' 之一。
        name: 资产的唯一名称 (不含扩展名)。
        content: 完整内容 (method/case 为 YAML，script 为 Python)。
    
    返回:
        成功消息及文件路径，或错误信息。
    
    示例:
        kb_save_pending('method', 'my_new_analysis', '<yaml content>')
        kb_save_pending('script', 'my_helper', '<python code>')
    """
    import datetime
    
    # Validate asset_type
    valid_types = {
        'method': ('methods', '.yaml'),
        'case': ('cases', '.yaml'),
        'script': ('scripts', '.py')
    }
    
    if asset_type not in valid_types:
        return f"Error: asset_type must be one of {list(valid_types.keys())}"
    
    subdir, ext = valid_types[asset_type]
    
    # Sanitize name
    safe_name = "".join(c for c in name if c.isalnum() or c in ('_', '-'))
    if not safe_name:
        return "Error: Invalid name. Use alphanumeric characters, underscores, or hyphens."
    
    # Build path
    pending_dir = os.path.join(_get_kb_base_dir(), 'knowledge', 'pending', subdir)
    os.makedirs(pending_dir, exist_ok=True)
    
    # Add timestamp to avoid conflicts
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{safe_name}_{timestamp}{ext}"
    filepath = os.path.join(pending_dir, filename)
    
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        result_msg = f"✅ Saved to pending review: {filepath}\n\nTo approve, move to: knowledge/{subdir}/{safe_name}{ext}"
        
        # For cases, also save to ChromaDB for semantic search
        if asset_type == 'case':
            try:
                import yaml
                case_data = yaml.safe_load(content)
                if case_data and case_data.get('root_cause'):
                    retriever = get_layered_retriever(_get_methods_dir(), _get_data_dir())
                    fingerprint = f"case_{safe_name}"
                    finding_data = {
                        "finding_summary": case_data.get('root_cause', ''),
                        "method_used": str(case_data.get('analysis_trace', [])),
                        "solution": case_data.get('solution', '')
                    }
                    node_id = retriever.match_or_save_node(fingerprint, finding_data)
                    result_msg += f"\n\n📊 Also indexed in ChromaDB (node: {node_id})"
            except Exception as e:
                logger.warning(f"Failed to index case in ChromaDB: {e}")
        
        return result_msg
    except Exception as e:
        logger.error(f"Failed to save pending asset: {e}")
        return f"Error saving asset: {e}"


def kb_record_failure(node_id: str) -> str:
    """[L3] Record that a finding path was a dead-end (Negative Feedback)."""
    retriever = get_layered_retriever(_get_methods_dir(), _get_data_dir())
    success = retriever.mark_node_failed(node_id)
    if success:
        return f"Node {node_id} marked as failed."
    return f"Error: Node {node_id} not found."


def kb_list_scripts(category: Optional[str] = None) -> str:
    """[Utility] 列出可用的 drgn 脚本。
    
    参数:
        category: 可选过滤 - 'analysis', 'lock', 'memory', 'utility'，或 None 显示全部。
    
    返回:
        脚本列表及使用示例。
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
    lines.append("# Set parameters (if any) and run script by name:")
    lines.append("run_drgn_command(\"lock_addr=0xffff...; lock_spinlock.py\")")
    lines.append("")
    lines.append("# Check script details and path:")
    lines.append("kb_get_script('lock_spinlock')")
    lines.append("```")
    
    return "\n".join(lines)


def _get_scripts_dir() -> str:
    """Get absolute path to scripts directory."""
    return os.path.join(_get_kb_base_dir(), 'knowledge', 'scripts', 'drgn')


def kb_get_script(script_name: str, show_code: bool = False) -> str:
    """[Utility] 获取 drgn 脚本的详情。
    
    参数:
        script_name: 脚本名称 (不含 .py 扩展名)。
        show_code: 如果为 True，返回完整源代码；默认 False (仅返回使用说明)。
    
    返回:
        脚本使用说明或源代码。
    """
    scripts_dir = _get_scripts_dir()
    path = os.path.join(scripts_dir, f"{script_name}.py")
    
    if not os.path.exists(path):
        available = kb_list_scripts()
        return f"Error: Script '{script_name}' not found.\n\n{available}"
    
    # Get metadata for usage example
    # We reuse the static info from list_scripts for now, or just generic
    # Ideally we should extract it from docstring, but let's keep it simple
    
    info_str = f"## Script: {script_name}.py\n"
    info_str += f"**Path**: `{path}`\n\n"
    
    if not show_code:
        info_str += "**Usage (via run_drgn_command)**:\n"
        info_str += "```python\n"
        info_str += f"# 1. Set parameters (if required)\n"
        info_str += f"# 2. Run script by name\n"
        info_str += f"run_drgn_command(\"<params>=...; {script_name}.py\")\n"
        info_str += "```\n\n"
        info_str += "> **Note**: To view full source code, call `kb_get_script('{script_name}', show_code=True)`."
        return info_str
    
    with open(path, 'r') as f:
        content = f.read()
    
    return f"{info_str}**Source Code**:\n```python\n{content}\n```"


def register(mcp: FastMCP):
    """Register Knowledge Base tools with MCP server."""
    mcp.tool()(kb_recommend_method)
    mcp.tool()(kb_get_method_guide)
    mcp.tool()(kb_search_history)
    # mcp.tool()(kb_record_finding)  # Hidden: use kb_save_pending('case', ...) instead
    mcp.tool()(kb_quick_start)
    mcp.tool()(kb_save_pending)
    # mcp.tool()(kb_record_failure)  # Hidden as per user request
    mcp.tool()(kb_list_scripts)
    mcp.tool()(kb_get_script)

