# Crash MCP Server

这是一个基于 MCP (Model Context Protocol) 的服务器，专门用于辅助 **系统崩溃转储 (Crash Dump)** 的分析。

它封装了 Linux 的 `crash` 实用程序，允许 AI 助手通过 MCP 协议自动发现转储文件、匹配内核、并执行交互式崩溃分析命令。

## 功能特性 (Features)

1.  **自动发现转储文件**:
    - 能够扫描指定目录（默认 `/var/crash`）下的 `vmcore`、`core` 等转储文件。
2.  **智能内核匹配**:
    - 尝试自动寻找与转储文件匹配的 `vmlinux` 内核文件（支持同目录查找）。
3.  **交互式 Crash 会话**:
    - 通过 `pexpect` 管理 `crash` 工具的交互式会话。
    - 支持长时间运行的会话，保持上下文。
4.  **MCP 工具集**:
    - `list_crash_dumps`: 列出可用的转储文件。
    - `start_crash_session`:启动一个新的分析会话。
    - `run_crash_command`: 在当前会话中执行任意 `crash` 命令 (如 `sys`, `bt`, `ps` 等)。
    - `get_sys_info`: 获取系统基本信息的快捷工具。
5.  **配置灵活**:
    - 支持通过 `.env` 文件配置浏览器（预留）和分析路径。

## 安装与使用 (Installation & Usage)

### 前置要求
- 系统需安装 Python 3.10+
- 系统需安装 `crash` 工具 (用于实际分析)
- 系统需安装 `pip` (Python 包管理器)

## 安装与使用 (Installation & Usage)

### 前置要求
- 系统需安装 Python 3.10+
- 系统需安装 `crash` 工具 (用于实际分析)
- 建议使用 Linux 环境 (Debian/Ubuntu)

### 1. 快速安装 (推荐)

我们提供了一个脚本来自动创建虚拟环境 (venv) 并安装依赖：

```bash
# 添加执行权限
chmod +x install.sh

# 运行安装脚本
./install.sh
```
> **注意**: 如果脚本提示缺少 `python3-venv`，请按提示安装：`sudo apt install python3-venv`

### 2. 手动安装 (Manual Install)

如果你更喜欢手动操作：

```bash
# 1. 创建虚拟环境
python3 -m venv venv

# 2. 激活环境
source venv/bin/activate

# 3. 安装依赖
pip install -e .
```

### 3. 配置

你可以复制示例配置文件并进行修改：
```bash
cp .env.example .env
```
主要配置项：
- `CRASH_SEARCH_PATH`: 崩溃转储文件的搜索路径（默认 `/var/crash`）。

### 4. 运行服务器

**命令行运行:**
```bash
# 先激活虚拟环境
source venv/bin/activate

# 启动服务器
crash-mcp
```

**在 Claude Desktop 中配置:**
在 `mcpServers` 配置中，直接指定虚拟环境中的 python 解释器路径：

```json
{
  "mcpServers": {
    "crash-analysis": {
      "command": "/path/to/your/crash-mcp/venv/bin/python",
      "args": ["-m", "crash_mcp.server"],
      "cwd": "/path/to/your/crash-mcp",
      "env": {
        "CRASH_SEARCH_PATH": "/var/crash"
      }
    }
  }
}
```

## 开发与测试

运行单元测试：
```bash
# 需要安装 test 依赖 (pytest)
pip install pytest
pytest
```
项目包含一个 `mock_crash.py` 脚本，用于在没有真实 `crash` 工具的环境下测试交互逻辑。
