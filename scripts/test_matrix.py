#!/usr/bin/env python3
"""Exercise every canvas preset against every layout in an isolated directory."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import os
from pathlib import Path

from PIL import Image

from validate_card_spec import CANVAS_PRESETS, LAYOUTS


SCRIPT_DIR = Path(__file__).resolve().parent
ZONES = [
    "upper-left", "upper-right", "middle-left", "middle-right", "lower-left",
    "lower-right", "upper-center", "lower-center", "center",
]


def main() -> int:
    python = sys.executable
    cases: list[dict[str, object]] = []
    keep_dir = os.environ.get("WHOLE_EARTH_MATRIX_DIR")
    context = None if keep_dir else tempfile.TemporaryDirectory(prefix="poemskills-card-matrix-")
    raw_dir = keep_dir or context.name
    try:
        root = Path(raw_dir)
        root.mkdir(parents=True, exist_ok=True)
        for preset_index, (preset, dimensions) in enumerate(CANVAS_PRESETS.items()):
            if preset == "custom":
                dimensions = (1376, 768)
            assert dimensions is not None
            width, height = dimensions
            for layout_index, layout in enumerate(sorted(LAYOUTS)):
                roles = ("interior", "cover") if layout == "text-led-note" else ("interior",)
                for role_index, card_role in enumerate(roles):
                    case_id = f"{preset}--{layout}--{card_role}"
                    title = "缩小问题\n今天开始"
                    body = (
                        "保留一个入口\n完成一个动作"
                        if card_role == "cover"
                        else "先只保留一个清楚入口\n再去完成一个可见动作"
                    )
                    spec = {
                        "card_role": card_role,
                        "source_ref": "画布矩阵测试原文",
                        "source_excerpt": "减少选择并保留一个入口，会让具体行动更容易开始。",
                        "card_claim": "缩小问题今天开始",
                        "series_id": "matrix",
                        "variant_id": case_id,
                        "card_number": role_index + 1,
                        "canvas_preset": preset,
                        "width": width,
                        "height": height,
                        "priority": "balanced",
                        "render_mode": "draft",
                        "layout": layout,
                        "cluster_zone": ZONES[(preset_index + layout_index + role_index) % len(ZONES)],
                        "paper": "pale-white-fiber",
                        "accent": "blue",
                        "title": title,
                        "body": body,
                        "assets": [{
                            "type": "silhouette" if layout == "silhouette-field" else "relief-print",
                            "subject": "从复杂枝叶中被清理出来的一条路径",
                            "semantic_role": "explain",
                            "semantic_reason": "用清晰路径解释减少选择后更容易开始具体行动",
                            "path": None,
                        }],
                        "annotations": ["FIELD NOTE / BEGIN", "remove · choose · act"],
                        "output": f"{case_id}.png",
                    }
                    spec_path = root / f"{case_id}.json"
                    spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
                    result = subprocess.run(
                        [python, str(SCRIPT_DIR / "run_pipeline.py"), "--legacy-v0.6", str(spec_path)],
                        text=True,
                        capture_output=True,
                    )
                    preview_path = root / f"{case_id}-preview.png"
                    qa_path = root / f"{case_id}.png.qa.json"
                    layout_path = root / f"{case_id}.png.layout.json"
                    preview_width = 0
                    preview_height = 0
                    mobile_metrics_valid = False
                    multiline_spacing_valid = False
                    if preview_path.is_file() and qa_path.is_file() and layout_path.is_file():
                        with Image.open(preview_path) as preview:
                            preview_width, preview_height = preview.size
                        qa = json.loads(qa_path.read_text(encoding="utf-8"))
                        layout_meta = json.loads(layout_path.read_text(encoding="utf-8"))
                        metrics = qa.get("metrics", {})
                        minimum_title_px = 20 if card_role == "cover" else 14
                        minimum_body_px = 11 if card_role == "cover" else 10
                        mobile_metrics_valid = (
                            metrics.get("thumbnail_title_px", 0) >= minimum_title_px
                            and metrics.get("thumbnail_body_px", 0) >= minimum_body_px
                        )
                        font_sizes = layout_meta.get("font_sizes", {})
                        title_boxes = sorted(layout_meta.get("title_boxes", []), key=lambda box: box[1])
                        body_boxes = sorted(layout_meta.get("body_boxes", []), key=lambda box: box[1])
                        title_pitch = [
                            later[1] - earlier[1]
                            for earlier, later in zip(title_boxes, title_boxes[1:])
                        ]
                        body_pitch = [
                            later[1] - earlier[1]
                            for earlier, later in zip(body_boxes, body_boxes[1:])
                        ]
                        # Ink-box tops vary slightly by glyph even when baseline pitch is fixed.
                        bearing_tolerance = 2
                        multiline_spacing_valid = (
                            len(title_boxes) >= 2
                            and len(body_boxes) >= 2
                            and all(
                                value + bearing_tolerance >= font_sizes.get("title", 0) * 1.4
                                for value in title_pitch
                            )
                            and all(
                                value + bearing_tolerance >= font_sizes.get("body", 0) * 1.5
                                for value in body_pitch
                            )
                        )
                    expected_preview_height = 500 if preset == "xhs-portrait" else round(height * 375 / width)
                    cases.append({
                        "case": case_id,
                        "valid": (
                            result.returncode == 0
                            and (preview_width, preview_height) == (375, expected_preview_height)
                            and mobile_metrics_valid
                            and multiline_spacing_valid
                        ),
                        "preview_width": preview_width,
                        "preview_height": preview_height,
                        "mobile_metrics_valid": mobile_metrics_valid,
                        "multiline_spacing_valid": multiline_spacing_valid,
                        "stdout": result.stdout[-1600:],
                        "stderr": result.stderr[-1600:],
                    })
    finally:
        if context is not None:
            context.cleanup()

    failures = [case for case in cases if not case["valid"]]
    print(json.dumps({"valid": not failures, "case_count": len(cases), "failures": failures}, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
