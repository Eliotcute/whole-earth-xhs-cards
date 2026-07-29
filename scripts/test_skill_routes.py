#!/usr/bin/env python3
"""Validate PoemSkills routing, specialist discovery, and brand isolation."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SPECIALISTS = ("poem-content", "poem-title", "poem-design", "poem-render", "poem-review")
BANNED_ACTIVE_TERMS = (
    "Whole Earth", "全球概览", "whole-earth", "古典互联网",
    "1970s independent catalog", "1970 年代反主流文化邮购目录",
)
ROOT_COMMAND_PATTERN = re.compile(
    r"^# (?P<host>Codex|Claude Code)\n(?P<command>POEMSKILLS_ROOT=.*)$",
    flags=re.MULTILINE,
)


def frontmatter_name(text: str) -> str | None:
    match = re.search(r"^name:\s*([^\n]+)$", text, flags=re.MULTILINE)
    return match.group(1).strip() if match else None


def main() -> int:
    router = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert frontmatter_name(router) == "poemskills"
    assert len(router.splitlines()) < 160
    root_commands: dict[str, str] | None = None
    for specialist in SPECIALISTS:
        assert f"`$%s`" % specialist in router
        skill_path = ROOT / "skills" / specialist / "SKILL.md"
        agent_path = ROOT / "skills" / specialist / "agents" / "openai.yaml"
        assert skill_path.is_file(), skill_path
        assert agent_path.is_file(), agent_path
        skill_text = skill_path.read_text(encoding="utf-8")
        assert frontmatter_name(skill_text) == specialist
        assert "PoemSkills" in skill_text.split("---", 2)[1]
        assert "POEMSKILLS_ROOT" in skill_text, f"missing resolved root guidance in {skill_path}"
        assert "<PoemSkills>" not in skill_text, f"unsafe shell placeholder remains in {skill_path}"
        assert "`scripts/" not in skill_text, f"cwd-dependent script path remains in {skill_path}"
        assert "python3 scripts/" not in skill_text, f"cwd-dependent command remains in {skill_path}"
        specialist_commands = {
            match.group("host"): match.group("command")
            for match in ROOT_COMMAND_PATTERN.finditer(skill_text)
        }
        assert set(specialist_commands) == {"Codex", "Claude Code"}, (
            f"missing executable host root commands in {skill_path}"
        )
        if root_commands is None:
            root_commands = specialist_commands
        else:
            assert specialist_commands == root_commands, f"root commands drifted in {skill_path}"

    assert root_commands is not None
    with tempfile.TemporaryDirectory() as temporary_dir:
        temporary_root = Path(temporary_dir).resolve()
        foreign_cwd = temporary_root / "foreign-cwd"
        foreign_cwd.mkdir()
        codex_home = temporary_root / "codex"
        claude_home = temporary_root / "claude"
        env = {
            **os.environ,
            "CODEX_HOME": str(codex_home),
            "CLAUDE_CONFIG_DIR": str(claude_home),
        }
        installed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "install_skills.py")],
            cwd=foreign_cwd,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        assert installed.returncode == 0, installed.stderr
        assert (codex_home / "skills" / "poem-content").is_symlink()
        assert (claude_home / "skills" / "poem-content").is_symlink()

        for host, command in root_commands.items():
            resolved = subprocess.run(
                [
                    "/bin/sh",
                    "-c",
                    "\n".join((
                        command,
                        'test -f "$POEMSKILLS_ROOT/SKILL.md" || exit 20',
                        'python3 "$POEMSKILLS_ROOT/scripts/validate_card_spec.py" --help >/dev/null || exit 21',
                        'printf "%s" "$POEMSKILLS_ROOT"',
                    )),
                ],
                cwd=foreign_cwd,
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
            assert resolved.returncode == 0, f"{host}: {resolved.stderr}"
            assert Path(resolved.stdout) == ROOT.resolve(), (host, resolved.stdout)

    active_files = [ROOT / "SKILL.md", ROOT / "README.md", *ROOT.glob("skills/*/SKILL.md")]
    active_files.extend([
        ROOT / "references" / "style-system.md",
        ROOT / "references" / "master-prompt.md",
        ROOT / "references" / "illustration-prompts.md",
    ])
    for path in active_files:
        text = path.read_text(encoding="utf-8")
        for term in BANNED_ACTIVE_TERMS:
            assert term not in text, f"legacy brand term {term!r} remains in {path}"

    route_examples = {
        "提炼长文": "poem-content",
        "封面标题": "poem-title",
        "配图": "poem-design",
        "导出 PNG": "poem-render",
        "能否发布": "poem-review",
    }
    for phrase, specialist in route_examples.items():
        assert phrase in router and specialist in router
    master_prompt = (ROOT / "references" / "master-prompt.md").read_text(encoding="utf-8")
    assert "只要文案和逐卡提示词" in master_prompt
    assert "每张卡片各有一条独立的最终合成提示词" in master_prompt
    assert "一条最终卡片合成提示词" not in master_prompt
    assert "Do not create a DesignPlan or CardSpec" in router
    assert "three total review rounds" in router
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for host in ("codex", "claude"):
        assert f"python3 scripts/install_skills.py --host {host}" in readme
        assert f"python3 scripts/install_skills.py --check --host {host}" in readme
    print("skill routes: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
