# Crash MCP Server

基于 MCP (Model Context Protocol) 的服务器，用于 **系统崩溃转储 (Crash Dump)** 分析。

集成 Linux `crash` 实用程序和 `drgn` 可编程调试器，提供统一分析接口。

## 功能特性

- **统一会话**: 同时支持 `crash` 和 `drgn` 引擎
- **会话去重**: 同一 vmcore 自动复用已有会话
- **命令持久化**: 输出自动落盘，支持分页和搜索
- **远程分析**: 通过 SSH 连接远程主机，无需下载 vmcore
- **多传输模式**: Stdio（默认） / SSE（HTTP）
- **智能架构识别**: 自动检测 vmcore 架构并选择对应的 crash 版本
- **自动编译**: 内置 crash 工具编译器，支持多架构和压缩格式

## 安装

### 前置要求
- Python 3.10+
- `crash` 工具（可通过内置编译器安装）
- `python3-dev` (编译 PyKdump 需要)
- `drgn` 工具（通过 pip 自动安装）

### 快速安装

```bash
chmod +x install.sh && ./install.sh
```

### 编译 Crash 工具

```bash
# 激活虚拟环境
source venv/bin/activate

# 查看依赖安装说明
compile-crash --deps

# 编译 x86_64 版本
compile-crash

# 编译 ARM64 版本（在 x86_64 上分析 ARM64 vmcore）
compile-crash --arch ARM64

# 编译带 PyKdump 支持的版本
compile-crash --pykdump-from-source
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

| 工具 | 说明 |
|------|------|
| `open_vmcore_session` | 打开 vmcore 崩溃转储文件进行分析 |
| `run_crash_command` | 执行 crash 命令，支持 PyKdump 扩展 |
| `run_drgn_command` | 执行 drgn Python 代码 |
| `close_vmcore_session` | 关闭当前分析会话 |
| `get_command_output` | 分页获取长命令输出 |
| `search_command_output` | 正则搜索命令输出 |
| `run_analysis_script` | 运行预定义分析脚本 (需配置 `DRGN_SCRIPTS_PATH`) |
| `list_analysis_scripts` | 列出可用分析脚本 (需配置 `DRGN_SCRIPTS_PATH`) |
| `get_crash_info` | 获取崩溃诊断报告 (需配置 `GET_DUMPINFO_SCRIPT`) |

### 配置

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `CRASH_EXTENSION_LOAD` | `true` | 是否自动加载扩展 |
| `CRASH_MCP_TRUNCATE_LINES` | `20` | 输出截断行数 |
| `CRASH_MCP_WORKDIR` | `/tmp/crash-mcp-sessions` | 会话工作目录 |
| `CRASH_MCP_CACHE` | `true` | 启用命令缓存 |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `GET_DUMPINFO_SCRIPT` | (空) | 自动化诊断脚本命令模板 (如 `python3 script.py {vmcore} {vmlinux}`) |
| `DRGN_SCRIPTS_PATH` | (空) | 外部 drgn 脚本搜索路径 (冒号分隔) |

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

## 示例

```python
# 本地分析
open_vmcore_session("/var/crash/vmcore", "/usr/lib/debug/vmlinux")
run_crash_command("bt")
run_crash_command("sys")
run_drgn_command("prog['init_task'].comm")

# 分页获取长输出
run_crash_command("ps")  # 返回 command_id
get_command_output("crash:ps", offset=20, limit=50)

# 搜索输出
search_command_output("crash:bt", "schedule")

# 远程分析
open_vmcore_session("/var/crash/vmcore", "/usr/lib/debug/vmlinux", 
              ssh_host="server-01", ssh_user="root")
```

## 常见问题

### 1. `no lzo compression support` 错误

vmcore 文件使用 LZO 压缩，但 crash 工具编译时未启用 LZO 支持。

```bash
sudo apt-get install liblzo2-dev
compile-crash --clean
```

### 2. 缺少 GMP/MPFR 库

```bash
sudo apt-get install libgmp-dev libmpfr-dev
```

### 3. 查看所有编译依赖

```bash
compile-crash --deps
```

## 许可证

[MIT License](LICENSE)
