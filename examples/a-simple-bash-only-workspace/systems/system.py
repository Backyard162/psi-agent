"""Build the system prompt for the bash-only agent workspace."""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import yaml


def _parse_yaml_header(content: str) -> tuple[dict | None, str]:
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not match:
        return None, content
    try:
        header = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return None, content
    body = content[match.end() :]
    return header, body


async def system_prompt_builder() -> str:
    current_file = Path(inspect.getfile(system_prompt_builder))
    workspace_root = current_file.parent.parent
    skills_dir = workspace_root / "skills"

    skills: list[str] = []
    if skills_dir.is_dir():
        for skill_dir in sorted(skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue
            header, _ = _parse_yaml_header(skill_md.read_text())
            if header and header.get("name") and header.get("description"):
                skills.append(f"- {header['name']}: {header['description']}")

    skills_text = "\n".join(skills) if skills else "(None)"

    return f"""You are a helpful AI assistant.

## Workspace
Location: {workspace_root}

## Skills
Location: {skills_dir}

Available:
{skills_text}"""
