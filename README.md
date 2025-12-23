# Crash MCP Server

这是一个基于 MCP (Model Context Protocol) 的服务器，专门用于辅助 **系统崩溃转储 (Crash Dump)** 的分析。

它集成了 Linux 的 `crash` 实用程序和 `drgn` 可编程调试器，提供统一的分析接口，支持本地和远程分析。

## 功能特性 (Features)

1.  **统一智能会话 (Unified Smart Session)**:
    - 同时启动 `crash` 和 `drgn` 引擎。
    - **智能路由**: 自动将命令分发给合适的引擎。
        - 常用命令 (`sys`, `bt`, `ps`) -> **Crash**
        - Python 代码 / API (`prog`, `find_task`) -> **Drgn**
        - 支持显式前缀: `crash: help`, `drgn: list(prog.tasks())`
2.  **远程分析 (Remote Execution)**:
    - 支持通过 SSH 连接远程主机进行分析。
    - 无需下载巨大的 `vmcore` 文件到本地。
3.  **多传输模式 (Transport Modes)**:
    - **Stdio**: 标准输入输出模式（默认）。
    - **SSE**: Server-Sent Events HTTP 模式，支持流式传输。
4.  **自动发现**:
    - 自动扫描指定目录（默认 `/var/crash`）下的转储文件。
    - 自动匹配 `vmlinux` 内核文件。

## 安装 (Installation)

### 前置要求
- Python 3.10+
- `crash` 工具 (目标主机需安装)
- `drgn` 工具 (目标主机需安装, 可选但推荐)
- SSH 客户端 (如果使用远程分析)

### 快速安装

```bash
# 运行安装脚本 (自动创建 venv 并安装依赖)
chmod +x install.sh
./install.sh
```

### 手动安装

```bash
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

## 使用指南 (Usage)

### 1. 启动服务器

**标准模式 (Stdio)** - *配合 Claude Desktop 或其他本地 LLM 客户端*:
```bash
crash-mcp
```

**SSE 模式 (HTTP)** - *配合远程客户端或 Web UI*:
```bash
crash-mcp --transport sse --port 8000
```

### 2. MCP 工具集

AI 助手可以使用以下工具：

- **`analyze_target(vmcore, vmlinux, ssh_host=None, ssh_user=None)`**:
    - 启动一个统一分析会话。
    - **本地分析**: 提供本地文件路径。
    - **远程分析**: 提供 `ssh_host` 和 `ssh_user`，以及**远程主机上**的文件路径。
- **`run_command(command, session_id)`**:
    - 执行分析命令。
    - 示例: `bt` (由 crash 执行), `prog['init_task']` (由 drgn 执行).
- **`list_crash_dumps()`**: 扫描本地转储文件。

### 3. 配置

复制 `.env.example` 到 `.env` 进行配置：
```bash
cp .env.example .env
```
- `CRASH_SEARCH_PATH`: 本地搜寻转储文件的路径。
- `LOG_LEVEL`: 日志级别 (INFO/DEBUG)。

### 4. 客户端配置 (Client Configuration)

**Claude Desktop 配置示例 (`claude_desktop_config.json`)**:

```json
{
  "mcpServers": {
    "crash-analysis": {
      "command": "/absolute/path/to/crash-mcp/venv/bin/crash-mcp",
      "args": ["--transport", "stdio"],
      "env": {
        "CRASH_SEARCH_PATH": "/var/crash"
      }
    }
  }
}
```

**SSE 连接信息 (SSE Connection Info)**:
如果你的客户端支持通过 HTTP/SSE 连接 (如 Web UI 或远程 MCP 客户端):
- **Server URL**: `http://localhost:8000/sse`
- **启动命令**: `crash-mcp --transport sse --port 8000`


## 示例 (Examples)

**场景 1: 本地分析**
```python
# 启动会话
analyze_target("/var/crash/127.0.0.1/vmcore", "/usr/lib/debug/vmlinux")

# 执行命令 (自动路由)
run_command("bt")                  # -> Crash: 打印堆栈
run_command("len(list(prog.tasks()))") # -> Drgn: 计算进程数
```

**场景 2: 远程分析**
```python
# 连接远程主机 server-01
analyze_target("/var/crash/vmcore", "/usr/lib/debug/vmlinux", 
               ssh_host="server-01", ssh_user="root")
```

## 许可证 (License)

[MIT License](LICENSE)
