# Crash MCP Server

基于 MCP (Model Context Protocol) 的服务器，用于 **系统崩溃转储 (Crash Dump)** 分析。

集成 Linux `crash` 实用程序和 `drgn` 可编程调试器，提供统一分析接口。

## 功能特性

- **统一会话**: 同时支持 `crash` 和 `drgn` 引擎
- **远程分析**: 通过 SSH 连接远程主机，无需下载 vmcore
- **多传输模式**: Stdio（默认） / SSE（HTTP）
- **自动发现**: 扫描指定目录下的转储文件
- **智能架构识别**: 自动检测 vmcore 架构并选择对应的 crash 版本
- **自动编译**: 内置 crash 工具编译器，支持多架构和压缩格式

## 安装

### 前置要求
- Python 3.10+
- `crash` 工具（可通过内置编译器安装）
- `drgn` 工具（可选，通过 pip 自动安装）

### 快速安装

```bash
chmod +x install.sh && ./install.sh
```

### 编译 Crash 工具

crash-mcp 内置了 crash 工具编译器，支持自动检测并启用压缩库（LZO、Snappy、Zstd），解决 vmcore 压缩格式兼容问题。

```bash
# 激活虚拟环境
source venv/bin/activate

# 查看依赖安装说明
compile-crash --deps

# 安装编译依赖（Ubuntu/Debian）
sudo apt-get install git make gcc g++ bison flex \
  zlib1g-dev libgmp-dev libmpfr-dev libncurses-dev \
  liblzma-dev texinfo liblzo2-dev libsnappy-dev libzstd-dev

# 编译 x86_64 版本（分析 x86_64 vmcore）
compile-crash

# 编译 ARM64 版本（在 x86_64 上分析 ARM64 vmcore）
compile-crash --arch ARM64

# 干净重新编译
compile-crash --arch ARM64 --clean
```

编译后的二进制文件位于 `./bin/` 目录:
- `crash` - x86_64 原生版本
- `crash-arm64` - ARM64 交叉调试版本

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
| `kb_list_scripts` | 列出辅助分析脚本 |
| `kb_get_script` | 获取脚本具体代码 |


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

### 作为 Resource 使用

你也可以直接在对话中引用 System Prompt 来查看其内容：
- **URI**: `crash-mcp://system_prompt`
- **使用方法**: 在支持 MCP Resource 的客户端（如 Claude Desktop）输入 `@system_prompt` 即可。

### 加载 System Prompt

服务器内置了专家级分析 Prompt。在 MCP 客户端（如 Claude Desktop）中：
1.  点击输入框附近的 **Prompt 库** 图标（通常是 `/` 或星星图标）。
2.  选择 `crash_analysis_prompt`。
3.  系统会自动填充标准工作流和工具说明，引导 AI 按照最佳实践进行分析。

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

## 常见问题

### 1. `no lzo compression support` 错误

vmcore 文件使用 LZO 压缩，但 crash 工具编译时未启用 LZO 支持。

**解决方法**:
```bash
# 安装 LZO 库
sudo apt-get install liblzo2-dev

# 重新编译 crash
compile-crash --arch ARM64 --clean
```

### 2. 缺少 GMP/MPFR 库

编译 crash 时提示 `Building GDB requires GMP 4.2+, and MPFR 3.1.0+`。

**解决方法**:
```bash
sudo apt-get install libgmp-dev libmpfr-dev
```

### 3. 查看所有编译依赖

```bash
compile-crash --deps
```

## 许可证

[MIT License](LICENSE)
