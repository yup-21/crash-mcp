---
trigger: manual
---

# MCP 开发规范

## 工具开发模板

```python
def my_tool(param: str, session_id: Optional[str] = None) -> str:
    """工具描述。"""
    try:
        target_id, session = get_session(session_id)
    except ValueError as e:
        return json_response("error", error=str(e))
    
    try:
        result = session.do_something(param)
        return json_response("success", {"key": result})
    except Exception as e:
        return json_response("error", error=str(e))

def register(mcp: FastMCP):
    mcp.tool()(my_tool)
```

## 核心规则

- **响应格式**：统一使用 `json_response("success", data)` 或 `json_response("error", error=msg)`
- **会话获取**：使用 `get_session(session_id)` 获取会话，`None` 表示最后一个会话
- **命令执行**：`session.execute_command()` 直接执行，`session.execute_with_store()` 带缓存
- **配置管理**：通过 `Config` 类读取，新配置用 `os.getenv()` 注册

## 添加新工具

1. 创建工具模块
2. 实现工具函数 + `register()` 函数
3. 在服务入口导入并注册