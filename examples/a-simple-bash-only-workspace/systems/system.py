"""Build the system prompt for the bash-only agent workspace."""

from __future__ import annotations

import inspect
from pathlib import Path


async def system_prompt_builder() -> str:
    current_file = Path(inspect.getfile(system_prompt_builder))
    workspace_root = current_file.parent.parent
    skills_dir = workspace_root / "skills"

    skills: list[str] = []
    if skills_dir.is_dir():
        for skill_dir in sorted(skills_dir.iterdir()):
            if skill_dir.is_dir():
                skill_md = skill_dir / "SKILL.md"
                if skill_md.exists():
                    skills.append(f"## {skill_dir.name}\n\n{skill_md.read_text()}")

    skills_text = "\n\n---\n\n".join(skills) if skills else "(No skills available)"

    return f"""You are a helpful AI assistant with access to a bash execution tool.

## Workspace
Location: {workspace_root}

## Available Tools
- **bash**: Execute bash commands and return the output.

## Available Skills
{skills_text}

## Guidelines
- Use the bash tool when you need to execute commands on the system.
- Explain what you're doing before running commands.
- Always consider safety - avoid destructive commands unless explicitly requested.
- Report results clearly and succinctly.
"""
