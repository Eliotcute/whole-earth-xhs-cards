#!/usr/bin/env python3
"""Regression tests for content-first roles and cover-specific rendering."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from validate_card_spec import validate


SCRIPT_DIR = Path(__file__).resolve().parent


def cover_spec(output: str = "cover.png") -> dict:
    return {
        "card_role": "cover",
        "source_ref": "用户提供的注意力原文",
        "source_excerpt": "减少无关入口，可以把注意力重新还给真正重要的事情。",
        "card_claim": "把注意力还给重要的事",
        "canvas_preset": "xhs-portrait",
        "width": 1242,
        "height": 1660,
        "priority": "balanced",
        "render_mode": "final",
        "layout": "text-led-note",
        "cluster_zone": "middle-left",
        "paper": "pale-white-fiber",
        "accent": "blue",
        "title": "把注意力还给\n重要的事",
        "body": "从减少一个无关入口开始管理注意力",
        "assets": [],
        "output": output,
    }


def main() -> int:
    base = cover_spec()
    missing_role = copy.deepcopy(base)
    missing_role.pop("card_role")
    wrong_claim = copy.deepcopy(base)
    wrong_claim["card_claim"] = "这不是实际渲染的封面标题"
    long_cover = copy.deepcopy(base)
    long_cover["title"] = long_cover["card_claim"] = "这是一个明显超过封面正常长度而且无法快速理解的标题"
    single_line = copy.deepcopy(base)
    single_line["title"] = "把注意力还给重要的事"
    bound_spec = copy.deepcopy(base)
    bound_spec.update({
        "contract": "poem-card-spec/v1",
        "status": "validated",
        "content_plan_digest": "a" * 64,
        "title_plan_digest": "b" * 64,
        "design_plan_digest": "c" * 64,
    })
    stale_bound_spec = copy.deepcopy(bound_spec)
    stale_bound_spec["title_plan_digest"] = "missing"
    oversized_custom = copy.deepcopy(base)
    oversized_custom.update({"canvas_preset": "custom", "width": 100000, "height": 100000})
    malformed_dimensions = copy.deepcopy(base)
    malformed_dimensions.update({"canvas_preset": "custom", "width": "not-a-number", "height": 1000})

    with tempfile.TemporaryDirectory(prefix="poemskills-content-contract-") as raw_root:
        root = Path(raw_root)
        outside_output = copy.deepcopy(base)
        outside_output["output"] = "../outside.png"
        outside_output_errors = validate(outside_output, root, allow_legacy=True)
        absolute_output = copy.deepcopy(base)
        absolute_output["output"] = str(root / "inside.png")
        absolute_output_errors = validate(absolute_output, root, allow_legacy=True)
        dotdot_output = copy.deepcopy(base)
        dotdot_output["output"] = "nested/../inside.png"
        dotdot_output_errors = validate(dotdot_output, root, allow_legacy=True)
        escape_link = root / "escape"
        escape_link.symlink_to(root.parent, target_is_directory=True)
        symlink_output = copy.deepcopy(base)
        symlink_output["output"] = "escape/outside.png"
        symlink_output_errors = validate(symlink_output, root, allow_legacy=True)
        spec_path = root / "cover.json"
        spec_path.write_text(json.dumps(base, ensure_ascii=False, indent=2), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "run_pipeline.py"), "--legacy-v0.6", str(spec_path)],
            text=True,
            capture_output=True,
        )
        meta = json.loads((root / "cover.png.layout.json").read_text(encoding="utf-8")) if result.returncode == 0 else {}
        qa = json.loads((root / "cover.png.qa.json").read_text(encoding="utf-8")) if result.returncode == 0 else {}

    valid = (
        bool(validate([]))
        and not validate(base, allow_legacy=True)
        and bool(validate(base))
        and bool(validate(missing_role, allow_legacy=True))
        and bool(validate(wrong_claim, allow_legacy=True))
        and bool(validate(long_cover, allow_legacy=True))
        and bool(validate(single_line, allow_legacy=True))
        and bool(validate(bound_spec))
        and bool(validate(stale_bound_spec))
        and bool(validate(oversized_custom, allow_legacy=True))
        and bool(validate(malformed_dimensions, allow_legacy=True))
        and any("must not contain '..'" in error for error in outside_output_errors)
        and any("must be relative" in error for error in absolute_output_errors)
        and any("must not contain '..'" in error for error in dotdot_output_errors)
        and any("must stay within" in error for error in symlink_output_errors)
        and result.returncode == 0
        and meta.get("card_role") == "cover"
        and meta.get("font_sizes", {}).get("title", 0) >= 68
        and qa.get("metrics", {}).get("thumbnail_title_px", 0) >= 20
    )
    print(json.dumps({
        "valid": valid,
        "non_object_rejected": bool(validate([])),
        "legacy_cover_accepted_with_flag": not validate(base, allow_legacy=True),
        "legacy_without_flag_rejected": bool(validate(base)),
        "missing_role_rejected": bool(validate(missing_role, allow_legacy=True)),
        "claim_mismatch_rejected": bool(validate(wrong_claim, allow_legacy=True)),
        "long_cover_rejected": bool(validate(long_cover, allow_legacy=True)),
        "single_line_xhs_cover_rejected": bool(validate(single_line, allow_legacy=True)),
        "v1_without_stage_refs_rejected": bool(validate(bound_spec)),
        "invalid_digest_rejected": bool(validate(stale_bound_spec)),
        "oversized_custom_rejected": bool(validate(oversized_custom, allow_legacy=True)),
        "malformed_dimensions_rejected": bool(validate(malformed_dimensions, allow_legacy=True)),
        "outside_output_rejected": any("must not contain '..'" in error for error in outside_output_errors),
        "absolute_output_rejected": any("must be relative" in error for error in absolute_output_errors),
        "dotdot_output_rejected": any("must not contain '..'" in error for error in dotdot_output_errors),
        "symlink_output_rejected": any("must stay within" in error for error in symlink_output_errors),
        "cover_title_px": meta.get("font_sizes", {}).get("title"),
        "thumbnail_title_px": qa.get("metrics", {}).get("thumbnail_title_px"),
    }, ensure_ascii=False, indent=2))
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
