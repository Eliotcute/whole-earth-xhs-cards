#!/usr/bin/env python3
"""Install the PoemSkills router and specialist skills as safe symlinks."""

from __future__ import annotations

import argparse
import fcntl
import os
import signal
import stat
import sys
from pathlib import Path


SKILL_PATHS = {
    "poemskills": Path("."),
    "poem-content": Path("skills/poem-content"),
    "poem-title": Path("skills/poem-title"),
    "poem-design": Path("skills/poem-design"),
    "poem-render": Path("skills/poem-render"),
    "poem-review": Path("skills/poem-review"),
}


def default_skills_dir() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    return Path(codex_home).expanduser() / "skills" if codex_home else Path.home() / ".codex" / "skills"


def host_skills_dirs(host: str) -> list[Path]:
    """Resolve one skills directory per requested host."""
    dirs: list[Path] = []
    if host in {"codex", "both"}:
        dirs.append(default_skills_dir())
    if host in {"claude", "both"}:
        claude_home = os.environ.get("CLAUDE_CONFIG_DIR")
        base = Path(claude_home).expanduser() if claude_home else Path.home() / ".claude"
        dirs.append(base / "skills")
    return dirs


InstallAction = tuple[str, Path, Path]


def prepare_target_dirs(raw_targets: list[Path]) -> tuple[list[Path], list[str]]:
    """Resolve, deduplicate, and reject targets hidden below managed links."""
    lexical_targets = [Path(os.path.abspath(raw_target.expanduser())) for raw_target in raw_targets]
    targets: list[Path] = []
    seen: set[Path] = set()
    for lexical_target in lexical_targets:
        target = lexical_target.resolve()
        if target not in seen:
            seen.add(target)
            targets.append(target)

    errors: list[str] = []
    for candidate_set in (lexical_targets, targets):
        for owner in candidate_set:
            managed_roots = tuple(owner / name for name in SKILL_PATHS)
            for candidate in candidate_set:
                if candidate == owner:
                    continue
                if any(candidate == managed or candidate.is_relative_to(managed) for managed in managed_roots):
                    message = f"skills directory cannot be nested below a managed skill link: {candidate}"
                    if message not in errors:
                        errors.append(message)
                    break
    return targets, errors


def plan_install(repo_root: Path, skills_dir: Path, check_only: bool = False) -> tuple[list[InstallAction], list[str], list[str]]:
    actions: list[InstallAction] = []
    messages: list[str] = []
    errors: list[str] = []
    for name, relative in SKILL_PATHS.items():
        source = (repo_root / relative).resolve()
        target = skills_dir / name
        if not (source / "SKILL.md").is_file():
            errors.append(f"missing source skill: {source}")
            continue
        if target.is_symlink():
            if target.resolve() != source:
                errors.append(f"refusing to replace unrelated symlink: {target}")
            elif not check_only:
                actions.append((name, source, target))
            else:
                messages.append(f"OK {name}: {target} -> {source}")
            continue
        if target.exists():
            errors.append(f"refusing to replace existing path: {target}")
            continue
        if check_only:
            errors.append(f"not installed: {target}")
            continue
        actions.append((name, source, target))
    return actions, messages, errors


def open_directory(path: Path) -> int:
    """Open a symlink-free directory path, creating missing components safely."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    descriptor = os.open(path.anchor, flags)
    try:
        for part in path.parts[1:]:
            try:
                child = os.open(part, flags, dir_fd=descriptor)
            except FileNotFoundError:
                os.mkdir(part, dir_fd=descriptor)
                child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def normalize_actions(actions: list[InstallAction]) -> tuple[list[InstallAction], list[str]]:
    normalized: list[InstallAction] = []
    seen_targets: set[Path] = set()
    errors: list[str] = []
    for name, source, target in actions:
        normalized_target = Path(os.path.abspath(target.expanduser()))
        if normalized_target in seen_targets:
            errors.append(f"installation plan contains a duplicate target: {normalized_target}")
            continue
        seen_targets.add(normalized_target)
        normalized.append((name, source.resolve(), normalized_target))
    return normalized, errors


def link_matches(parent_fd: int, target: Path, source: Path) -> bool:
    try:
        target_stat = os.stat(target.name, dir_fd=parent_fd, follow_symlinks=False)
        raw_link = Path(os.readlink(target.name, dir_fd=parent_fd))
    except OSError:
        return False
    if not stat.S_ISLNK(target_stat.st_mode):
        return False
    resolved_link = raw_link.resolve() if raw_link.is_absolute() else (target.parent / raw_link).resolve()
    return resolved_link == source


def apply_install(actions: list[InstallAction]) -> tuple[list[str], list[str]]:
    normalized_actions, normalization_errors = normalize_actions(actions)
    if normalization_errors:
        return [], normalization_errors

    parent_fds: dict[Path, int] = {}
    unique_fds: list[int] = []
    fds_by_identity: dict[tuple[int, int], int] = {}
    messages: list[str] = []
    installed_count = 0
    try:
        for parent in sorted({target.parent for _, _, target in normalized_actions}, key=str):
            descriptor = open_directory(parent)
            try:
                descriptor_stat = os.fstat(descriptor)
                identity = (descriptor_stat.st_dev, descriptor_stat.st_ino)
                existing_descriptor = fds_by_identity.get(identity)
                if existing_descriptor is not None:
                    os.close(descriptor)
                    descriptor = existing_descriptor
                else:
                    fcntl.flock(descriptor, fcntl.LOCK_EX)
                    fds_by_identity[identity] = descriptor
                    unique_fds.append(descriptor)
            except BaseException:
                os.close(descriptor)
                raise
            parent_fds[parent] = descriptor

        target_keys: set[tuple[int, int, str]] = set()
        pending: list[InstallAction] = []
        preflight_errors: list[str] = []
        for name, source, target in normalized_actions:
            parent_fd = parent_fds[target.parent]
            parent_stat = os.fstat(parent_fd)
            key = (parent_stat.st_dev, parent_stat.st_ino, target.name)
            if key in target_keys:
                preflight_errors.append(f"installation plan contains a duplicate target: {target}")
                continue
            target_keys.add(key)
            try:
                target_stat = os.stat(target.name, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                pending.append((name, source, target))
                continue
            if not stat.S_ISLNK(target_stat.st_mode):
                preflight_errors.append(f"refusing to replace existing path: {target}")
            elif not link_matches(parent_fd, target, source):
                preflight_errors.append(f"refusing to replace unrelated symlink: {target}")
            else:
                messages.append(f"OK {name}: {target} -> {source}")

        for parent, descriptor in parent_fds.items():
            try:
                current = os.stat(parent, follow_symlinks=False)
                opened = os.fstat(descriptor)
            except OSError as exc:
                preflight_errors.append(f"skills directory changed during install: {parent}: {exc}")
                continue
            if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
                preflight_errors.append(f"skills directory changed during install: {parent}")
        if preflight_errors:
            return [], preflight_errors

        blocked_signals = {
            candidate
            for candidate in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
            if candidate is not None
        }
        previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, blocked_signals)
        try:
            for name, source, target in pending:
                os.symlink(source, target.name, target_is_directory=True, dir_fd=parent_fds[target.parent])
                installed_count += 1
                messages.append(f"INSTALLED {name}: {target} -> {source}")

            for parent, descriptor in parent_fds.items():
                current = os.stat(parent, follow_symlinks=False)
                opened = os.fstat(descriptor)
                if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
                    raise RuntimeError(f"skills directory changed during install: {parent}")
            for _, source, target in normalized_actions:
                if not link_matches(parent_fds[target.parent], target, source):
                    raise RuntimeError(f"installed skill link changed during install: {target}")
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
    except BaseException as exc:
        if installed_count:
            failure = f"installation stopped after a write failure: {type(exc).__name__}: {exc}"
            retry = "successfully created links were preserved; rerun the installer to complete safely"
            return messages, [failure, retry]
        return [], [f"installation failed before writing links: {type(exc).__name__}: {exc}"]
    finally:
        for descriptor in unique_fds:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)
    return messages, []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skills-dir", type=Path, default=None)
    parser.add_argument("--host", choices=("codex", "claude", "both"), default="both")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parent.parent
    if args.skills_dir is not None:
        raw_targets = [args.skills_dir]
    else:
        raw_targets = host_skills_dirs(args.host)
    targets, target_errors = prepare_target_dirs(raw_targets)
    actions: list[InstallAction] = []
    messages: list[str] = []
    errors: list[str] = list(target_errors)
    for skills_dir in targets:
        planned, planned_messages, planned_errors = plan_install(
            repo_root, skills_dir, args.check,
        )
        actions.extend(planned)
        messages.extend(planned_messages)
        errors.extend(planned_errors)
    for message in messages:
        print(message)
    if errors:
        for error in errors:
            print(f"ERROR {error}", file=sys.stderr)
        return 1
    installed_messages, apply_errors = apply_install(actions)
    for message in installed_messages:
        print(message)
    if apply_errors:
        for error in apply_errors:
            print(f"ERROR {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
