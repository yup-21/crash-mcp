# Crash MCP Server

基于 MCP (Model Context Protocol) 的服务器，用于 **系统崩溃转储 (Crash Dump)** 分析。

集成 Linux `crash` 实用程序和 `drgn` 可编程调试器，提供统一分析接口。

## 功能特性

- **统一会话**: 同时支持 `crash` 和 `drgn` 引擎
- **远程分析**: 通过 SSH 连接远程主机，无需下载 vmcore
- **多传输模式**: Stdio（默认） / SSE（HTTP）
- **自动发现**: 扫描指定目录下的转储文件

## 安装

### 前置要求
- Python 3.10+
- `crash` 工具
- `drgn` 工具（可选）

### 快速安装

```bash
chmod +x install.sh && ./install.sh
```

## 使用

### 启动服务器

```bash
# Stdio 模式
crash-mcp

# SSE 模式
crash-mcp --transport sse --port 8000
```

### MCP 工具

**Session 工具**:
| 工具 | 说明 |
|------|------|
| `list_crash_dumps` | 扫描目录查找 vmcore 文件 |
| `start_session` | 启动分析会话 |
| `run_crash_command` | 执行 crash 命令 |
| `run_drgn_command` | 执行 drgn Python 代码 |
| `stop_session` | 关闭会话 |
| `get_sys_info` | 获取系统信息 |

**Knowledge Base 工具**:
| 工具 | 说明 |
|------|------|
| `kb_search_symptom` | L1 语义搜索匹配分析方法 |
| `kb_analyze_method` | L2 获取方法执行上下文 |
| `kb_search_subproblem` | L3 基于上下文搜索案例子树 |
| `kb_match_or_save_node` | L3 案例节点匹配/创建 |
| `kb_mark_node_failed` | L3 负反馈标记 |
| `kb_run_workflow` | 快速启动分析工作流 |

### 配置

```bash
cp .env.example .env
```

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `CRASH_SEARCH_PATH` | `/var/crash` | 搜索转储文件的路径 |
| `KB_BASE_DIR` | `""` (项目根目录) | 知识库/数据根目录 |
| `KB_SIMILARITY_THRESHOLD` | `0.2` | 向量匹配阈值 |
| `KB_EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | 嵌入模型 |
| `LOG_LEVEL` | `INFO` | 日志级别 |

### 客户端配置

**Claude Desktop** (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "crash-analysis": {
      "command": "/path/to/crash-mcp/venv/bin/crash-mcp"
    }
  }
}
```

**SSE 连接**: `http://localhost:8000/sse`

## 示例

```python
# 本地分析
start_session("/var/crash/vmcore", "/usr/lib/debug/vmlinux")
run_crash_command("bt")
run_drgn_command("prog.crashed_thread()")

# 远程分析
start_session("/var/crash/vmcore", "/usr/lib/debug/vmlinux", 
              ssh_host="server-01", ssh_user="root")
```

## 许可证

[MIT License](LICENSE)
