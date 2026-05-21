from __future__ import annotations

"""Full end-to-end integration tests with mock AI — uses direct SSE API."""

import json
import signal
import subprocess
import time
from pathlib import Path

import pytest
from aiohttp import web

from tests.integration.conftest import MockAIServer, read_sse  # noqa: E402


def _chunk(
    content: str = "",
    reasoning: str = "",
    tool_calls: list | None = None,
    finish_reason: str | None = None,
) -> str:
    d: dict = {}
    if content:
        d["content"] = content
    if reasoning:
        d["reasoning_content"] = reasoning
    if tool_calls:
        d["tool_calls"] = tool_calls
    return json.dumps(
        {
            "id": "test",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "test",
            "choices": [{"index": 0, "delta": d, "finish_reason": finish_reason}],
        }
    )


def _wait_for_socket(sock_path: Path, timeout_sec: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if sock_path.exists():
            time.sleep(0.3)
            return True
        time.sleep(0.1)
    return False


@pytest.mark.anyio
async def test_full_pipeline_mock_ai(tmp_path: Path, mock_ai_server: MockAIServer) -> None:
    """Full pipeline: mock AI → session → SSE read."""
    mock_ai_server.set_responses([_chunk(content="pipeline works", finish_reason="stop")])
    base_url = await mock_ai_server.start()

    ai_socket = tmp_path / "ai.sock"
    channel_socket = tmp_path / "channel.sock"

    ai_proc = subprocess.Popen(
        [
            "uv",
            "run",
            "psi-agent",
            "ai",
            "openai-completions",
            "--session-socket",
            str(ai_socket),
            "--model",
            "test",
            "--api-key",
            "k",
            "--base-url",
            base_url,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    ses_proc = subprocess.Popen(
        [
            "uv",
            "run",
            "psi-agent",
            "session",
            "--workspace",
            "examples/a-simple-bash-only-workspace",
            "--channel-socket",
            str(channel_socket),
            "--ai-socket",
            str(ai_socket),
            "--model",
            "test",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        assert _wait_for_socket(ai_socket)
        assert _wait_for_socket(channel_socket)

        chunks = await read_sse(str(channel_socket), "test pipeline")
        content = "".join(c.get("choices", [{}])[0].get("delta", {}).get("content", "") for c in chunks)
        assert "pipeline works" in content, f"Got: {content[:200]}"
    finally:
        for p in [ses_proc, ai_proc]:
            p.send_signal(signal.SIGTERM)
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()


@pytest.mark.anyio
async def test_full_pipeline_with_tool(tmp_path: Path) -> None:
    """Full pipeline with tool call: mock AI → tool execution → final response."""
    import socket as _sock

    req_count = 0

    async def handler(request: web.Request) -> web.StreamResponse:
        nonlocal req_count
        req_count += 1
        resp = web.StreamResponse(status=200, reason="OK", headers={"Content-Type": "text/event-stream"})
        await resp.prepare(request)
        if req_count == 1:
            tc = _chunk(
                tool_calls=[
                    {
                        "index": 0,
                        "id": "c1",
                        "type": "function",
                        "function": {
                            "name": "echo",
                            "arguments": '{"message":"tool test"}',
                        },
                    }
                ],
                finish_reason="tool_calls",
            )
            await resp.write(f"data: {tc}\n\n".encode())
        else:
            await resp.write(f"data: {_chunk(content='Final: tool was called', finish_reason='stop')}\n\n".encode())
        await resp.write(b"data: [DONE]\n\n")
        return resp

    app = web.Application()
    app.router.add_post("/v1/chat/completions", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    sock = _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    site = web.SockSite(runner, sock)
    await site.start()

    ai_socket = tmp_path / "ai.sock"
    channel_socket = tmp_path / "channel.sock"

    ai_proc = subprocess.Popen(
        [
            "uv",
            "run",
            "psi-agent",
            "ai",
            "openai-completions",
            "--session-socket",
            str(ai_socket),
            "--model",
            "test",
            "--api-key",
            "k",
            "--base-url",
            f"http://127.0.0.1:{port}/v1",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    ses_proc = subprocess.Popen(
        [
            "uv",
            "run",
            "psi-agent",
            "session",
            "--workspace",
            "examples/a-simple-bash-only-workspace",
            "--channel-socket",
            str(channel_socket),
            "--ai-socket",
            str(ai_socket),
            "--model",
            "test",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        assert _wait_for_socket(ai_socket)
        assert _wait_for_socket(channel_socket)
        chunks = await read_sse(str(channel_socket), "use tool")
        all_text = json.dumps(chunks)
        assert "tool was called" in all_text, f"Got: {all_text[:500]}"
    finally:
        for p in [ses_proc, ai_proc]:
            p.send_signal(signal.SIGTERM)
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        await runner.cleanup()


@pytest.mark.anyio
async def test_multiple_messages_history_accumulates(tmp_path: Path) -> None:
    """Two channel messages should cause history accumulation in session."""
    import socket as _sock

    req_count = 0

    async def handler(request: web.Request) -> web.StreamResponse:
        nonlocal req_count
        req_count += 1
        resp = web.StreamResponse(status=200, reason="OK", headers={"Content-Type": "text/event-stream"})
        await resp.prepare(request)
        await resp.write(f"data: {_chunk(content=f'response {req_count}', finish_reason='stop')}\n\n".encode())
        await resp.write(b"data: [DONE]\n\n")
        return resp

    app = web.Application()
    app.router.add_post("/v1/chat/completions", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    sock = _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    site = web.SockSite(runner, sock)
    await site.start()

    ai_socket = tmp_path / "ai.sock"
    channel_socket = tmp_path / "channel.sock"

    ai_proc = subprocess.Popen(
        [
            "uv",
            "run",
            "psi-agent",
            "ai",
            "openai-completions",
            "--session-socket",
            str(ai_socket),
            "--model",
            "test",
            "--api-key",
            "k",
            "--base-url",
            f"http://127.0.0.1:{port}/v1",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    ses_proc = subprocess.Popen(
        [
            "uv",
            "run",
            "psi-agent",
            "session",
            "--workspace",
            "examples/a-simple-bash-only-workspace",
            "--channel-socket",
            str(channel_socket),
            "--ai-socket",
            str(ai_socket),
            "--model",
            "test",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        assert _wait_for_socket(ai_socket)
        assert _wait_for_socket(channel_socket)
        chunks1 = await read_sse(str(channel_socket), "msg1")
        time.sleep(0.3)
        chunks2 = await read_sse(str(channel_socket), "msg2")
        c1 = "".join(c.get("choices", [{}])[0].get("delta", {}).get("content", "") for c in chunks1)
        c2 = "".join(c.get("choices", [{}])[0].get("delta", {}).get("content", "") for c in chunks2)
        assert "response 1" in c1, f"Got: {c1}"
        assert "response 2" in c2, f"Got: {c2}"
    finally:
        for p in [ses_proc, ai_proc]:
            p.send_signal(signal.SIGTERM)
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        await runner.cleanup()
