from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

import anyio
from loguru import logger

from psi_agent._logging import setup_logging
from psi_agent.channel._core import ChannelCore
from psi_agent.channel._types import TextChunk
from psi_agent.session import Session


async def call_agent(
    workspace: str,
    ai_socket: str,
    message: str,
    verbose: bool = False,
) -> str:
    """Start a session, send a message, and return the agent's response.

    Creates a temporary Session with its own channel socket, sends
    ``message`` to the agent defined by ``workspace``, and collects
    the full response as a string.

    The session is torn down automatically before returning.
    """
    channel_socket = f"/tmp/psi-call-{uuid.uuid4().hex}.sock"

    session = Session(
        workspace=workspace,
        channel_socket=channel_socket,
        ai_socket=ai_socket,
        verbose=verbose,
    )

    result_parts: list[str] = []

    async with anyio.create_task_group() as tg:
        tg.start_soon(session.run)

        await _wait_for_socket(channel_socket)

        try:
            async with ChannelCore(channel_socket, interval=0.0) as core:
                async for chunk in core.post([TextChunk(message)]):
                    if isinstance(chunk, TextChunk):
                        result_parts.append(chunk.text)
        finally:
            tg.cancel_scope.cancel()

    return "".join(result_parts)


@dataclass
class Call:
    """Start a session, send a message, print the response to stdout, then exit."""

    workspace: str
    """Path to the workspace directory."""

    ai_socket: str
    """Path to the AI Unix domain socket."""

    message: str
    """Message to send to the agent."""

    verbose: bool = False
    """Enable DEBUG-level logging."""

    async def run(self) -> None:
        setup_logging(verbose=self.verbose)
        try:
            text = await call_agent(
                workspace=self.workspace,
                ai_socket=self.ai_socket,
                message=self.message,
                verbose=self.verbose,
            )
            print(text)
        except Exception as e:
            logger.error(f"Call error: {e}")
            print(f"\n[Error: {e}]")


async def _wait_for_socket(path: str, timeout: float = 10.0, poll_interval: float = 0.05) -> None:
    """Wait until a Unix socket file appears at ``path``."""
    deadline = time.monotonic() + timeout
    while True:
        if await anyio.Path(path).exists():
            await anyio.sleep(0.3)
            return
        if time.monotonic() > deadline:
            raise TimeoutError(f"Socket {path} did not appear within {timeout}s")
        await anyio.sleep(poll_interval)
