# 问题记录：`--verbose` 污染 `base_url` 导致上游 404

## 场景

在配置 multi-agent math solver 示例的 `run-multi-agent.yml` 时，ai 块的配置如下：

```yaml
- type: ai
  session_socket: /tmp/ai.sock
  provider: openai
  model: deepseek-v4-flash-ascend
  api_key: sk-xxx
  base_url: https://api.llm.ustc.edu.cn/v1 --verbose
```

## 表现

运行后收到 404 错误：

```
Error forwarding to upstream: Error code: 404 - {'detail': 'Not Found'}
```

## 排查过程

1. 确认 API key 和 base_url 均是有效的（单独用三个终端的方式可以正常工作）
2. 检查 AI 后端的 DEBUG 日志，发现请求的 URL 异常
3. 发现 `base_url` 的值是 `https://api.llm.ustc.edu.cn/v1 --verbose`
4. `any-llm-sdk` 在此 URL 后拼接 `/chat/completions`，最终请求了：
   `https://api.llm.ustc.edu.cn/v1 --verbose/chat/completions`
5. 该 URL 不是合法 HTTP 路径，上游返回 404

## 根因

YAML 文件的手工撰写过程中，误把本应是独立字段的 `--verbose` CLI 标志直接写入了 `base_url` 的字符串值中。

`_run.py` 的 `_run_config()` 通过 `Ai(**item)` 将 YAML 键值对直接映射到 `Ai` dataclass 的字段，不做任何输入校验或类型清洗。因此此类手写错误会被原样传递到 SDK 层。

## 修复

将 `--verbose` 从 `base_url` 行移除，改为独立的 `verbose` 字段：

```yaml
# 修复前
  base_url: https://api.llm.ustc.edu.cn/v1 --verbose

# 修复后
  base_url: https://api.llm.ustc.edu.cn/v1
  verbose: true
```

## 启示

YAML 配置中字符串类型的字段不具有 CLI 的 flag 解析能力。`base_url` 是纯字符串，不应包含任何 CLI 标志（如 `--verbose`）。如需开启 DEBUG 日志，应使用 `verbose: true` 独立字段。
