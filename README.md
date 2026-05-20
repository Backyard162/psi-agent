# psi-agent

微内核式 Python Agent 框架。三个独立组件——ai、session、channel——通过 Unix domain socket 以 OpenAI-compatible HTTP/SSE 协议通信。

## 设计理念

- **微内核**: 核心极简，功能由 workspace 定义
- **无状态组件**: ai/session/channel 各自独立，通过 socket 组合
- **全异步**: 所有 IO 使用 anyio，永不使用 pathlib
- **充分日志**: loguru 全覆盖，每个 chunk 可追踪
- **现代 Python**: 3.14+，无历史包袱

## 架构

```
Channel (REPL/CLI) ←→ Session ←→ AI (OpenAI/Anthropic)
                   Unix socket  Unix socket
```

三个组件各自独立启动，通过 socket 路径连接。

## 快速开始

```bash
# 1. 安装
uv sync

# 2. 启动 AI 后端（使用 OpenRouter）
uv run psi-agent ai openai-completions \
  --session-socket ./ai.sock \
  --model openai/gpt-4.1 \
  --api-key sk-or-v1-xxxx

# 3. 启动 Session（另一个终端）
uv run psi-agent session \
  --workspace ./examples/a-simple-bash-only-workspace \
  --channel-socket ./channel.sock \
  --ai-socket ./ai.sock

# 4. 使用 CLI channel 发送消息
uv run psi-agent channel cli \
  --session-socket ./channel.sock \
  --message "列出当前目录的文件"
```

## CLI 结构

```
psi-agent
├── ai
│   ├── openai-completions    # OpenAI 兼容后端
│   └── anthropic-messages    # Anthropic→OpenAI 转换后端
├── session                    # Session 管理
└── channel
    ├── repl                   # 交互式 REPL
    └── cli                    # 单次消息 CLI
```

## Workspace 结构

```
workspace/
├── tools/           # *.py 文件定义 tool 函数
├── skills/          # */SKILL.md 技能文档
├── schedules/       # */TASK.md 定时任务
└── systems/
    └── system.py    # system_prompt_builder() 函数
```

### Tool 定义

```python
# tools/my_tool.py
async def my_tool(param1: str, param2: int = 10) -> str:
    """Tool 描述。

    Args:
        param1: 参数1说明。
        param2: 参数2说明。
    """
    return "result"
```

### 定时任务

```markdown
---
name: task-name
cron: "0 12 * * *"
---
任务内容，会被作为消息发送给 AI。
```

## 开发

```bash
uv run ruff check .      # lint
uv run ruff format .     # format
uv run pytest -v         # 测试
uv build                 # 构建
```

## 许可

MIT
