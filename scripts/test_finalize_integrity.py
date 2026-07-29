#!/usr/bin/env python3
"""Regression tests that finalization is bound to current spec and pixel QA."""

from __future__ import annotations

import json
import stat
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
CATEGORIES = (
    "semantic_specificity", "material_quality", "paper_tactility", "composition",
    "typography", "image_text_relationship", "negative_space", "series_rhythm",
    "mobile_readability", "provenance_restraint",
)


def run(spec: Path, finalize: bool = False) -> subprocess.CompletedProcess[str]:
    args = [sys.executable, str(SCRIPT_DIR / "run_pipeline.py"), "--legacy-v0.6"]
    if finalize:
        args.append("--finalize")
    args.append(str(spec))
    return subprocess.run(args, text=True, capture_output=True)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="poemskills-finalize-") as raw_root:
        root = Path(raw_root)
        title = "把注意力还给\n重要的事"
        payload = {
            "card_role": "cover",
            "source_ref": "用户提供的注意力原文",
            "source_excerpt": "减少无关入口，可以把注意力重新还给真正重要的事情。",
            "card_claim": title,
            "canvas_preset": "xhs-portrait",
            "width": 1242,
            "height": 1660,
            "priority": "balanced",
            "render_mode": "final",
            "layout": "text-led-note",
            "cluster_zone": "middle-left",
            "paper": "pale-white-fiber",
            "accent": "blue",
            "title": title,
            "body": "从减少一个无关入口开始\n把注意力还给真正重要的事情",
            "assets": [],
            "output": "cover.png",
        }
        spec = root / "cover.json"
        spec.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        rendered = run(spec)
        try:
            rendered_manifest = json.loads(rendered.stdout)
        except json.JSONDecodeError:
            rendered_manifest = {}
        manifest_path = root / "artifact-manifest.json"
        manifest_written = manifest_path.is_file()
        qa_path = root / "cover.png.qa.json"
        qa = json.loads(qa_path.read_text(encoding="utf-8")) if qa_path.exists() else {}

        review_path = root / "cover.png.visual-review.json"
        generated_paths = (
            root / "cover.png",
            root / "cover-preview.png",
            root / "cover.png.layout.json",
            qa_path,
            review_path,
            manifest_path,
        )
        generated_modes = {
            path.name: stat.S_IMODE(path.stat().st_mode) for path in generated_paths if path.exists()
        }
        publish_permissions_valid = (
            len(generated_modes) == len(generated_paths)
            and all(mode == 0o644 for mode in generated_modes.values())
        )
        review = json.loads(review_path.read_text(encoding="utf-8"))
        review.update({
            "status": "approved",
            "scores": {category: 8.5 for category in CATEGORIES},
            "lowest_category": "composition",
            "revision_summary": "检查完整图片与手机预览，并确认封面字号、留白和图文关系。",
            "approved": True,
        })
        review_path.write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
        layout_path = root / "cover.png.layout.json"
        original_layout = layout_path.read_text(encoding="utf-8")
        layout = json.loads(original_layout)
        title_boxes = layout.get("title_boxes", [])
        title_line_pitch = title_boxes[1][1] - title_boxes[0][1] if len(title_boxes) > 1 else 0
        title_spacing_valid = title_line_pitch >= layout.get("font_sizes", {}).get("title", 0) * 1.4
        body_boxes = layout.get("body_boxes", [])
        body_line_pitch = body_boxes[1][1] - body_boxes[0][1] if len(body_boxes) > 1 else 0
        body_spacing_valid = body_line_pitch >= layout.get("font_sizes", {}).get("body", 0) * 1.5
        contrast_metrics = qa.get("metrics", {})
        contrast_values = [contrast_metrics.get("title_contrast"), contrast_metrics.get("body_contrast")]
        contrast_metrics_valid = (
            all(isinstance(value, (int, float)) and value >= 4.5 for value in contrast_values)
            and contrast_metrics.get("essential_contrast") == min(contrast_values)
        )
        mobile_metrics_valid = (
            contrast_metrics.get("thumbnail_title_px", 0) >= 20
            and contrast_metrics.get("thumbnail_body_px", 0) >= 10
        )
        layout["tampered_after_qa"] = True
        layout_path.write_text(json.dumps(layout, ensure_ascii=False, indent=2), encoding="utf-8")
        stale_layout = run(spec, finalize=True)
        layout_path.write_text(original_layout, encoding="utf-8")
        finalized = run(spec, finalize=True)

        payload["source_excerpt"] = "修改后的来源摘录仍然有效，但已不再对应原来的像素检查。"
        spec.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        stale_spec = run(spec, finalize=True)

        payload["source_excerpt"] = "减少无关入口，可以把注意力重新还给真正重要的事情。"
        spec.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        (root / "cover.png.qa.json").unlink()
        missing_qa = run(spec, finalize=True)

    valid = (
        rendered.returncode == 0
        and rendered_manifest.get("contract") == "poem-artifact-manifest/v1"
        and manifest_written
        and publish_permissions_valid
        and bool(qa.get("layout_sha256"))
        and title_spacing_valid
        and body_spacing_valid
        and contrast_metrics_valid
        and mobile_metrics_valid
        and stale_layout.returncode != 0
        and finalized.returncode == 0
        and stale_spec.returncode != 0
        and missing_qa.returncode != 0
    )
    print(json.dumps({
        "valid": valid,
        "render_passed": rendered.returncode == 0,
        "stdout_is_manifest_json": rendered_manifest.get("contract") == "poem-artifact-manifest/v1",
        "manifest_written": manifest_written,
        "generated_modes": {name: oct(mode) for name, mode in generated_modes.items()},
        "publish_permissions_valid": publish_permissions_valid,
        "layout_bound_to_qa": bool(qa.get("layout_sha256")),
        "title_line_pitch": title_line_pitch,
        "title_spacing_valid": title_spacing_valid,
        "body_line_pitch": body_line_pitch,
        "body_spacing_valid": body_spacing_valid,
        "contrast_metrics_valid": contrast_metrics_valid,
        "mobile_metrics_valid": mobile_metrics_valid,
        "stale_layout_rejected": stale_layout.returncode != 0,
        "finalize_passed": finalized.returncode == 0,
        "stale_spec_rejected": stale_spec.returncode != 0,
        "missing_qa_rejected": missing_qa.returncode != 0,
    }, ensure_ascii=False, indent=2))
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
