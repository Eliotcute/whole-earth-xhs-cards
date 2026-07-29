#!/usr/bin/env python3
"""Integration tests for safe PoemSkills installation and check mode."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

from install_skills import SKILL_PATHS, apply_install, prepare_target_dirs


ROOT = Path(__file__).resolve().parent.parent
INSTALLER = ROOT / "scripts" / "install_skills.py"
SKILL_NAMES = ("poemskills", "poem-content", "poem-title", "poem-design", "poem-render", "poem-review")


def run_installer(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(INSTALLER), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as temporary_dir:
        temporary_root = Path(temporary_dir).resolve()
        codex_home = temporary_root / "codex"
        claude_home = temporary_root / "claude"
        env = {
            **os.environ,
            "CODEX_HOME": str(codex_home),
            "CLAUDE_CONFIG_DIR": str(claude_home),
        }
        target_dirs = (codex_home / "skills", claude_home / "skills")

        missing = run_installer("--check", env=env)
        assert missing.returncode == 1
        assert all(not target.exists() for target in target_dirs), "--check must not create target directories"
        assert missing.stderr.count("not installed:") == len(SKILL_NAMES) * len(target_dirs)

        installed = run_installer(env=env)
        assert installed.returncode == 0, installed.stderr
        assert all((target / name).is_symlink() for target in target_dirs for name in SKILL_NAMES)
        assert all(
            (target / name).resolve() == (ROOT / relative).resolve()
            for target in target_dirs
            for name, relative in SKILL_PATHS.items()
        )

        checked = run_installer("--check", env=env)
        assert checked.returncode == 0, checked.stderr
        assert checked.stdout.count("OK ") == len(SKILL_NAMES) * len(target_dirs)

        codex_only = temporary_root / "codex-only"
        claude_unused = temporary_root / "claude-unused"
        single_env = {
            **os.environ,
            "CODEX_HOME": str(codex_only),
            "CLAUDE_CONFIG_DIR": str(claude_unused),
        }
        single = run_installer("--host", "codex", env=single_env)
        assert single.returncode == 0, single.stderr
        assert all((codex_only / "skills" / name).is_symlink() for name in SKILL_NAMES)
        assert not claude_unused.exists()

        shared_home = temporary_root / "shared-home"
        shared_env = {
            **os.environ,
            "CODEX_HOME": str(shared_home),
            "CLAUDE_CONFIG_DIR": str(shared_home),
        }
        shared = run_installer(env=shared_env)
        assert shared.returncode == 0, shared.stderr
        assert shared.stdout.count("INSTALLED ") == len(SKILL_NAMES)

        nested_targets, nested_errors = prepare_target_dirs([
            temporary_root / "nested" / "skills",
            temporary_root / "nested" / "skills" / "poemskills" / "injected" / "skills",
        ])
        assert len(nested_targets) == 2
        assert nested_errors and "nested below a managed skill link" in nested_errors[0]

        atomic_codex = temporary_root / "atomic-codex"
        atomic_claude = temporary_root / "atomic-claude"
        conflict = atomic_claude / "skills" / "poem-content"
        conflict.mkdir(parents=True)
        atomic_env = {
            **os.environ,
            "CODEX_HOME": str(atomic_codex),
            "CLAUDE_CONFIG_DIR": str(atomic_claude),
        }
        blocked = run_installer(env=atomic_env)
        assert blocked.returncode == 1
        assert not (atomic_codex / "skills").exists(), "failed dual-host install must not modify the first host"
        assert not (atomic_claude / "skills" / "poemskills").exists(), "preflight must run before creating links"
        assert conflict.is_dir() and not conflict.is_symlink()

        custom_skills = temporary_root / "custom-skills"
        unrelated_source = temporary_root / "unrelated-source"
        unrelated_source.mkdir()
        custom_skills.mkdir()
        unrelated_link = custom_skills / "poem-title"
        unrelated_link.symlink_to(unrelated_source, target_is_directory=True)
        refused = run_installer("--skills-dir", str(custom_skills))
        assert refused.returncode == 1
        assert unrelated_link.resolve() == unrelated_source.resolve()
        assert not (custom_skills / "poemskills").exists()

        apply_root = temporary_root / "apply-failure"
        blocked_parent = temporary_root / "blocked-parent"
        blocked_parent.write_text("not a directory", encoding="utf-8")
        actions = [
            ("first", ROOT, apply_root / "skills" / "first"),
            ("second", ROOT, blocked_parent / "second"),
        ]
        apply_messages, apply_errors = apply_install(actions)
        assert not apply_messages and apply_errors
        assert not (apply_root / "skills" / "first").exists(), "write-time rollback must remove created links"

        interrupt_root = temporary_root / "interrupt"
        interrupt_actions = [
            ("first", ROOT, interrupt_root / "first"),
            ("second", ROOT, interrupt_root / "second"),
        ]
        original_symlink = os.symlink

        def interrupt_second(source, destination, target_is_directory=False, *, dir_fd=None) -> None:
            if destination == "second":
                raise KeyboardInterrupt()
            original_symlink(
                source,
                destination,
                target_is_directory=target_is_directory,
                dir_fd=dir_fd,
            )

        with mock.patch("install_skills.os.symlink", new=interrupt_second):
            interrupt_messages, interrupt_errors = apply_install(interrupt_actions)
        assert interrupt_messages and interrupt_errors
        assert (interrupt_root / "first").is_symlink(), "completed links must remain safe for an idempotent retry"
        assert not (interrupt_root / "second").exists()
        retry_messages, retry_errors = apply_install(interrupt_actions)
        assert not retry_errors
        assert any(message.startswith("OK first:") for message in retry_messages)
        assert (interrupt_root / "second").is_symlink()

        replacement_root = temporary_root / "replacement"
        first_target = replacement_root / "first"
        replacement_actions = [
            ("first", ROOT, first_target),
            ("second", ROOT, replacement_root / "second"),
        ]

        def replace_then_fail(source, destination, target_is_directory=False, *, dir_fd=None) -> None:
            if destination == "second":
                first_target.unlink()
                first_target.write_text("concurrent replacement", encoding="utf-8")
                raise OSError("forced failure after replacement")
            original_symlink(
                source,
                destination,
                target_is_directory=target_is_directory,
                dir_fd=dir_fd,
            )

        with mock.patch("install_skills.os.symlink", new=replace_then_fail):
            replacement_messages, replacement_errors = apply_install(replacement_actions)
        assert replacement_messages and replacement_errors
        assert first_target.read_text(encoding="utf-8") == "concurrent replacement"
        assert any("preserved" in error for error in replacement_errors)

        redirected_root = temporary_root / "redirected-target"
        redirected_root.mkdir()
        redirected_target = redirected_root / "poemskills"
        redirect_destination = temporary_root / "redirect-destination" / "poemskills"
        redirected_target.symlink_to(redirect_destination, target_is_directory=True)
        redirected_messages, redirected_errors = apply_install([
            ("redirected", ROOT, redirected_target),
        ])
        assert not redirected_messages and redirected_errors
        assert redirected_target.is_symlink()
        assert not redirect_destination.exists(), "apply must not follow a final target symlink"

        injected_parent = temporary_root / "injected-parent"
        injected_parent.mkdir()
        parent_target = injected_parent / "poemskills"
        redirected_parent = temporary_root / "redirected-parent"
        redirected_parent.mkdir()
        injected_parent.rmdir()
        injected_parent.symlink_to(redirected_parent, target_is_directory=True)
        parent_messages, parent_errors = apply_install([
            ("redirected-parent", ROOT, parent_target),
        ])
        assert not parent_messages and parent_errors
        assert not (redirected_parent / "poemskills").exists(), "apply must not follow a replaced parent"

        renamed_parent = temporary_root / "renamed-parent"
        renamed_target = renamed_parent / "poemskills"
        moved_parent = temporary_root / "moved-parent"
        original_symlink = os.symlink

        def rename_after_create(source, destination, target_is_directory=False, *, dir_fd=None) -> None:
            original_symlink(source, destination, target_is_directory=target_is_directory, dir_fd=dir_fd)
            renamed_parent.rename(moved_parent)
            renamed_parent.mkdir()

        with mock.patch("install_skills.os.symlink", new=rename_after_create):
            renamed_messages, renamed_errors = apply_install([
                ("renamed", ROOT, renamed_target),
            ])
        assert renamed_messages and renamed_errors
        assert not renamed_target.exists() and (moved_parent / "poemskills").is_symlink()
        assert any("directory changed" in error for error in renamed_errors)

    print("skill installation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
