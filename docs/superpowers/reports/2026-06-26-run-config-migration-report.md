# psi-agent run config.yml 迁移报告

## 一、Config YAML 的使用方式

### 基本原理

`psi-agent run config.yml` 通过 `_run.py` 的 `_run_config()` 读取 YAML 列表，按 `type` 字段分别实例化 `Ai`、`Session`、`ChannelCli`/`ChannelRepl`/`ChannelTelegram`，然后在同一个 `anyio.create_task_group()` 中并发启动——效果与手动开多个终端窗口等价。

### 用户只需提供「厂家 + API Key」的场景

当用户只告知 `provider` 和 `api_key` 时，agent 需要根据厂家信息自动补全 `model` 和 `base_url` 的默认值。以下是常见厂商的默认映射表：

| Provider 名称 | 默认 base_url | 常见 model |
|--------------|--------------|-----------|
| `openai` | `https://api.openai.com/v1` | `gpt-4o-mini` |
| `anthropic` | `https://api.anthropic.com` | `claude-sonnet-4-20250514` |
| `deepseek` | `https://api.deepseek.com` | `deepseek-chat` |
| `gemini` | 由 SDK 自动处理 | `gemini-2.0-flash` |
| `moonshot`（Kimi） | `https://api.moonshot.ai/v1` | `moonshot-v1-8k` |

以用户说「我用 OpenAI，Key 是 sk-xxx」为例，agent 应自动生成：

```yaml
- type: ai
  session_socket: /tmp/ai.sock
  provider: openai
  model: gpt-4o-mini
  api_key: sk-xxx
  base_url: https://api.openai.com/v1
```

如果用户用的是兼容 OpenAI 格式的第三方 API（如我们使用的 `https://api.llm.ustc.edu.cn/v1`），用户需额外提供 `base_url`，`provider` 仍填 `openai`。

### 多 agent 场景的完整 config 示例

```yaml
- type: ai                        # AI 后端（共享）
  session_socket: /tmp/ai.sock
  provider: openai
  model: gpt-4o-mini
  api_key: sk-xxx
  base_url: https://api.openai.com/v1

- type: session                   # 子 agent 1
  workspace: ./reasoning
  channel_socket: /tmp/reasoning.sock
  ai_socket: /tmp/ai.sock

- type: session                   # 子 agent 2
  workspace: ./coding
  channel_socket: /tmp/coding.sock
  ai_socket: /tmp/ai.sock

- type: session                   # 主 agent
  workspace: ./orchestrator
  channel_socket: /tmp/orchestrator.sock
  ai_socket: /tmp/ai.sock

- type: channel                   # 用户入口
  name: repl
  session_socket: /tmp/orchestrator.sock
```

启动命令：

```bash
rm -f /tmp/*.sock
psi-agent run config.yml
```

---

## 二、问题发现：`Ai` dataclass 不接受 extra params

### 现象

在编写上述 YAML 配置时，我们曾尝试在 `type: ai` 块中加入 `temperature`、`max_tokens` 等常见 LLM 参数，例如：

```yaml
- type: ai
  session_socket: /tmp/ai.sock
  provider: openai
  model: gpt-4o-mini
  api_key: sk-xxx
  base_url: https://api.openai.com/v1
  temperature: 0.7        # 合法，但会报错
```

### 原因

`src/psi_agent/ai/__init__.py` 中 `Ai` dataclass 的字段是固定的：

```python
@dataclass
class Ai:
    session_socket: str
    provider: str = ""
    model: str = ""
    api_key: str = ""
    base_url: str = ""
    verbose: bool = False
```

`_run.py` 通过 `Ai(**item)` 实例化，任何不在上述列表中的字段都会导致 `TypeError: unexpected keyword argument 'temperature'`。

### 矛盾点

与此同时，`ai/server.py` 的 `handle_chat_completions()` 在处理会话层发来的请求时，确实支持额外参数透传：

```python
await acompletion(provider=provider, model=model, messages=messages,
                  stream=True, api_key=api_key, api_base=base_url, **body)
```

也就是说：extra params 可以从 Channel → Session → AI 的请求路径传入，但不能从 YAML 的 ai 配置块传入。

### 影响

如果用户想为某个 AI 后端设定固定的 `temperature` 或 `max_completion_tokens`，目前无法在 `config.yml` 中直接配置，只能在每个 Session 发起的请求中附带。
