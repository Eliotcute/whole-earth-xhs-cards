#!/usr/bin/env python3
"""Regression tests for adjacent rhythm and independent series outputs."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def card(number: int, layout: str, zone: str, output: str) -> dict:
    title = "每张卡片都要保留一个独立论点"
    return {
        "card_role": "interior",
        "source_ref": "系列节奏测试原文",
        "source_excerpt": "相邻卡片可以保留一种视觉机制，但不能同时重复布局和焦点。",
        "card_claim": title,
        "series_id": "series-test",
        "variant_id": "xhs",
        "card_number": number,
        "canvas_preset": "xhs-portrait",
        "width": 1242,
        "height": 1660,
        "priority": "balanced",
        "render_mode": "draft",
        "layout": layout,
        "cluster_zone": zone,
        "title": title,
        "body": "同一布局可以切换焦点，同一焦点也可以切换布局；只有两者同时重复时才破坏相邻节奏。",
        "assets": [],
        "output": output,
    }


def run_case(root: Path, name: str, cards: list[dict]) -> bool:
    paths = []
    for index, payload in enumerate(cards, start=1):
        path = root / f"{name}-{index}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        paths.append(path)
    result = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "validate_series.py"), *map(str, paths)],
        text=True,
        capture_output=True,
    )
    return result.returncode == 0


def invalid_json_rejected(paths: list[Path]) -> bool:
    result = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "validate_series.py"), *map(str, paths)],
        text=True,
        capture_output=True,
    )
    combined_output = result.stdout + result.stderr
    return (
        result.returncode == 1
        and result.stdout.startswith("INVALID\n- ")
        and "Traceback" not in combined_output
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="poemskills-series-contract-") as raw_root:
        root = Path(raw_root)
        first = card(1, "quiet-specimen", "middle-left", "one.png")
        same_layout = card(2, "quiet-specimen", "middle-right", "two.png")
        same_zone = card(2, "text-led-note", "middle-left", "two.png")
        repeated_both = card(2, "quiet-specimen", "middle-left", "two.png")
        duplicate_output = copy.deepcopy(same_layout)
        duplicate_output["output"] = "one.png"

        valid_path = root / "valid.json"
        valid_path.write_text(json.dumps(first, ensure_ascii=False), encoding="utf-8")
        missing_path = root / "missing.json"
        malformed_path = root / "malformed.json"
        malformed_path.write_text("{", encoding="utf-8")
        oversized_path = root / "oversized.json"
        oversized_path.write_bytes(b" " * 1_000_001)

        same_layout_ok = run_case(root, "same-layout", [first, same_layout])
        same_zone_ok = run_case(root, "same-zone", [first, same_zone])
        repeated_both_ok = run_case(root, "repeated-both", [first, repeated_both])
        duplicate_output_ok = run_case(root, "duplicate-output", [first, duplicate_output])
        missing_json_rejected = invalid_json_rejected([missing_path, valid_path])
        malformed_json_rejected = invalid_json_rejected([malformed_path, valid_path])
        oversized_json_rejected = invalid_json_rejected([oversized_path, valid_path])

    valid = (
        same_layout_ok
        and same_zone_ok
        and not repeated_both_ok
        and not duplicate_output_ok
        and missing_json_rejected
        and malformed_json_rejected
        and oversized_json_rejected
    )
    print(json.dumps({
        "valid": valid,
        "same_layout_new_zone_allowed": same_layout_ok,
        "same_zone_new_layout_allowed": same_zone_ok,
        "same_layout_and_zone_rejected": not repeated_both_ok,
        "duplicate_output_rejected": not duplicate_output_ok,
        "missing_json_rejected_without_traceback": missing_json_rejected,
        "malformed_json_rejected_without_traceback": malformed_json_rejected,
        "oversized_json_rejected_without_traceback": oversized_json_rejected,
    }, ensure_ascii=False, indent=2))
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
