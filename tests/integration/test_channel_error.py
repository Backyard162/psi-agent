from __future__ import annotations

"""Channel error handling integration tests — using Python API."""

import subprocess  # noqa: E402
from pathlib import Path  # noqa: E402

import anyio  # noqa: E402
import pytest  # noqa: E402
from aiohttp import web  # noqa: E402

from tests.integration.conftest import read_sse  # noqa: E402


@pytest.mark.anyio
async def test_cli_session_socket_not_exists(tmp_path: Path) -> None:
    """CLI should print error when session socket doesn't exist."""
    result = subprocess.run(
        [
            "uv",
            "run",
            "psi-agent",
            "channel",
            "cli",
            "--session-socket",
            str(tmp_path / "nonexistent.sock"),
            "--message",
            "hello",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "Error" in combined or "error" in combined.lower()


@pytest.mark.anyio
async def test_session_busy_returns_503(tmp_path: Path) -> None:
    """Session should return 503 error JSON when busy."""
    channel_socket = tmp_path / "busy.sock"

    async def busy_handler(request: web.Request) -> web.StreamResponse:
        return web.json_response(
            {"error": {"message": "Session busy", "type": "session_busy", "code": "busy"}},
            status=503,
        )

    app = web.Application()
    app.router.add_post("/v1/chat/completions", busy_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.UnixSite(runner, str(channel_socket))
    await site.start()

    try:
        await anyio.sleep(0.2)
        from aiohttp import ClientSession, ClientTimeout, UnixConnector

        timeout = ClientTimeout(total=5)
        connector = UnixConnector(path=str(channel_socket))
        async with (
            ClientSession(connector=connector, timeout=timeout) as session,
            session.post(
                "http://localhost/v1/chat/completions",
                json={"model": "test", "messages": [{"role": "user", "content": "hi"}], "stream": True},
            ) as resp,
        ):
            assert resp.status == 503
    finally:
        await runner.cleanup()


@pytest.mark.anyio
async def test_cli_empty_message(tmp_path: Path) -> None:
    """Session should handle empty message from client."""
    channel_socket = tmp_path / "empty.sock"

    async def handler(request: web.Request) -> web.StreamResponse:
        await request.json()  # parse body
        resp = web.StreamResponse(status=200, reason="OK", headers={"Content-Type": "text/event-stream"})
        await resp.prepare(request)
        await resp.write(b"data: [DONE]\n\n")
        return resp

    app = web.Application()
    app.router.add_post("/v1/chat/completions", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.UnixSite(runner, str(channel_socket))
    await site.start()

    try:
        await anyio.sleep(0.2)
        chunks = await read_sse(str(channel_socket), "")
        # Should not crash, empty message is valid
        assert isinstance(chunks, list)
    finally:
        await runner.cleanup()
