"""Execute bash commands."""

from __future__ import annotations

import anyio
from loguru import logger


async def bash(command: str) -> str:
    """Execute a bash command and return the combined stdout and stderr output.

    Args:
        command: The bash command to execute. Use with caution.
    """
    logger.info(f"Executing bash command: {command}")
    try:
        result = await anyio.run_process(["/bin/bash", "-c", command])
        stdout = result.stdout.decode().strip()
        stderr = result.stderr.decode().strip()
        output = stdout
        if stderr:
            output += f"\n[stderr]\n{stderr}"
        output = output.strip() or "(no output)"
        logger.debug(f"Bash result: {output[:200]}")
        return output
    except Exception as e:
        logger.error(f"Bash command failed: {e}")
        return f"Error executing command: {e}"
