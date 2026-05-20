# AGENTS.md

本文档面向后续开发者（人或 AI Agent），说明 psi-agent 的设计思路、代码结构和开发约定。

## 设计理念

psi-agent 是一个**微内核**式的 agent 框架。核心理念是：

1. **最小化核心**: 框架本身只提供通信协议、组件组合和 tool/Schedule 加载机制
2. **功能由 workspace 定义**: agent 的能力（tools、system prompt、定时任务）完全由 workspace 目录中的文件定义
3. **组件无状态**: AI 后端不保存任何状态；Session 只维护一个内存中的 history；Channel 不管理历史
4. **组合优于继承**: 三个独立组件通过 Unix socket 任意组合
5. **一切异步**: 所有 IO 操作使用 `anyio`，永不使用 `asyncio` 原生 API 或 `pathlib`

## 代码结构

```
psi_agent/
├── cli.py                  # tyro CLI 入口，定义 top-level Union
├── logging.py              # loguru 配置，verbose→DEBUG
├── protocol.py             # OpenAI 兼容协议 dataclass
├── ai/
│   ├── openai_completions/ # OpenAI→OpenAI 透传后端
│   └── anthropic_messages/ # Anthropic→OpenAI 转换后端
├── session/
│   ├── __init__.py         # SessionConfig dataclass + run()
│   ├── server.py           # channel 端 aiohttp server
│   ├── agent.py            # 核心 agent loop
│   ├── tools.py            # workspace tools 加载
│   ├── scheduler.py        # cron-based 定时任务
│   └── workspace.py        # (未来) workspace 统一管理
└── channel/
    ├── repl/               # 交互式 REPL channel
    └── cli/                # 单次消息 CLI channel
```

## 核心通信协议

所有组件通过 **aiohttp Unix socket** 以 **OpenAI Chat Completions HTTP/SSE** 格式通信：

- **AI socket**: Session 作为客户端访问，`POST /v1/chat/completions`
- **Channel socket**: Session 作为服务端，`POST /v1/chat/completions`

SSE 流中的特殊字段：
- `delta.content` — AI 最终文本回复
- `delta.reasoning_content` — 聚合了 AI thinking + tool_call 意图 + tool_call 结果
- `delta.tool_calls` — 部分 tool call 定义（流式累积）

错误响应格式（OpenAI 风格）：
```json
{"error": {"message": "...", "type": "...", "code": "..."}}
```

## Agent Loop 逻辑

1. 收到 channel 请求
2. 检查暂存的 schedule 响应 → 有则先流式返回
3. 获取 `anyio.Lock`（忙则返回 503 + error JSON）
4. User message 追加到 history
5. 发送 `history + tools` 到 AI socket（streaming）
6. 解析 SSE 流：
   - content → yield 给 channel
   - reasoning_content → yield 给 channel
   - tool_calls → 累积
   - finish_reason="tool_calls" → 执行 tool → 结果追加到 history → 回到步骤 5
   - finish_reason="stop" → 最终 content 追加到 history → 释放锁
7. 最多 10 轮 tool call

## Tool 加载约定

- `workspace/tools/*.py` 中的每个 `.py` 文件
- 找到**与文件名同名**的 `async def` 函数
- 用 `inspect.signature()` 提取参数（类型注解 → JSON Schema 类型）
- 用 `inspect.getdoc()` 提取描述（支持 Google-style 的 `Args:` 格式）
- 函数必须是 async、非私有

## Anthropic 转换细节

- System message → Anthropic `system` 字段
- Assistant tool_calls → Anthropic `tool_use` content blocks
- Tool result → Anthropic `tool_result` content blocks
- Anthropic `thinking_delta` → OpenAI `reasoning_content`
- Anthropic `text_delta` → OpenAI `content`
- Anthropic `input_json_delta` → OpenAI partial `tool_calls` delta

## 日志约定

- 所有模块使用 `from loguru import logger`
- 默认 INFO 级别，`--verbose` 开启 DEBUG
- DEBUG 必须覆盖：每个 SSE chunk、tool 执行、锁获取/释放
- 格式：`时间 | 级别 | 模块:函数:行号 - 消息`

## 测试约定

- 使用 `pytest` + `pytest-asyncio`（`asyncio_mode = "auto"`）
- 异步测试用 `@pytest.mark.anyio`
- 测试目录结构镜像 `psi_agent/`
- Mock AI socket 用 `aiohttp.web.Application` + `UnixSite`/`TCPSite`

## 开发命令

```bash
uv run ruff check .          # lint 检查
uv run ruff check --fix .    # auto-fix
uv run ruff format .         # 格式化
uv run pytest -v             # 运行测试
uv run psi-agent --help      # CLI 帮助
uv build                     # 构建
```

## 未来扩展方向

- [ ] 单进程中运行多个 session 实例（利用 anyio task group）
- [ ] workspace.py 统一 workspace 管理
- [ ] 更多 channel 类型（WebSocket、HTTP API 等）
- [ ] 更多 AI 后端（Gemini、本地模型等）
- [ ] Session history 持久化（可选）
- [ ] Channel 广播/多客户端队列
