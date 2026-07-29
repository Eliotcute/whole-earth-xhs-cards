#!/usr/bin/env python3
"""Verify vertical editorial layouts through rendered geometry."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def render_case(root: Path, layout: str) -> tuple[subprocess.CompletedProcess[str], dict]:
    output = root / f"{layout}.png"
    spec = {
        "card_role": "interior",
        "source_ref": "垂直编辑版式测试原文",
        "source_excerpt": "图片与文字的上下次序必须和用户选择的版式完全一致。",
        "card_claim": "版式选择必须真实兑现",
        "canvas_preset": "xhs-portrait",
        "width": 1242,
        "height": 1660,
        "priority": "balanced",
        "render_mode": "draft",
        "layout": layout,
        "cluster_zone": "center",
        "paper": "pale-white-fiber",
        "accent": "blue",
        "title": "版式选择必须真实兑现",
        "body": "当用户选择图片在上或文字在上时，最终坐标关系不能被静默替换。",
        "assets": [{
            "type": "color-block",
            "motif": "sequence",
            "subject": "上下次序示意",
            "semantic_role": "sequence",
            "semantic_reason": "用顺序图形解释图片与文字的上下阅读次序",
        }],
        "output": output.name,
    }
    spec_path = root / f"{layout}.json"
    spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "run_pipeline.py"), "--legacy-v0.6", str(spec_path)],
        text=True,
        capture_output=True,
    )
    meta_path = output.with_suffix(output.suffix + ".layout.json")
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    return result, meta


def render_cover_without_subtitle(root: Path) -> tuple[subprocess.CompletedProcess[str], dict]:
    output = root / "cover-without-subtitle.png"
    spec = {
        "card_role": "cover",
        "source_ref": "无副标题封面测试原文",
        "source_excerpt": "封面可以只使用主标题，不必强制添加副标题。",
        "card_claim": "告别分心重建专注力",
        "canvas_preset": "xhs-portrait",
        "width": 1242,
        "height": 1660,
        "priority": "balanced",
        "render_mode": "draft",
        "layout": "quiet-specimen",
        "cluster_zone": "center",
        "paper": "pale-white-fiber",
        "accent": "blue",
        "title": "告别分心\n重建专注力",
        "body": "",
        "assets": [{
            "type": "color-block",
            "motif": "boundary",
            "subject": "专注边界",
            "semantic_role": "symbolize-specific-idea",
            "semantic_reason": "用边界图形表达从分心切换到专注的主题",
        }],
        "output": output.name,
    }
    spec_path = root / "cover-without-subtitle.json"
    spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "run_pipeline.py"), "--legacy-v0.6", str(spec_path)],
        text=True,
        capture_output=True,
    )
    meta_path = output.with_suffix(output.suffix + ".layout.json")
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    return result, meta


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="poemskills-layout-contracts-") as raw_root:
        root = Path(raw_root)
        image_result, image_meta = render_case(root, "image-above")
        text_result, text_meta = render_case(root, "text-above")
        cover_result, cover_meta = render_cover_without_subtitle(root)

        image_asset = image_meta.get("asset_boxes", [[0, 0, 0, 99999]])[0]
        image_text = image_meta.get("title_boxes", []) + image_meta.get("body_boxes", [])
        text_asset = text_meta.get("asset_boxes", [[0, 0, 0, 0]])[0]
        text_copy = text_meta.get("title_boxes", []) + text_meta.get("body_boxes", [])
        image_above = bool(image_text) and image_asset[3] < min(box[1] for box in image_text)
        text_above = bool(text_copy) and max(box[3] for box in text_copy) < text_asset[1]
        cover_without_subtitle = cover_result.returncode == 0 and cover_meta.get("body_boxes") == []

        image_meta["body_boxes"] = []
        image_meta_path = root / "image-above.png.layout.json"
        image_meta_path.write_text(json.dumps(image_meta, ensure_ascii=False, indent=2), encoding="utf-8")
        missing_interior_body = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "qa_card.py"),
                str(root / "image-above.json"),
                str(root / "image-above.png"),
            ],
            text=True,
            capture_output=True,
        )
        try:
            missing_interior_body_errors = json.loads(missing_interior_body.stdout).get("errors", [])
        except json.JSONDecodeError:
            missing_interior_body_errors = []
        missing_interior_body_rejected = (
            missing_interior_body.returncode != 0
            and "body_boxes must contain rendered text evidence" in missing_interior_body_errors
        )
        valid = (
            image_result.returncode == 0 and text_result.returncode == 0
            and image_above and text_above and cover_without_subtitle
            and missing_interior_body_rejected
        )
        print(json.dumps({
            "valid": valid,
            "image_above_rendered": image_result.returncode == 0,
            "text_above_rendered": text_result.returncode == 0,
            "image_above_geometry": image_above,
            "text_above_geometry": text_above,
            "cover_without_subtitle_valid": cover_without_subtitle,
            "missing_interior_body_rejected": missing_interior_body_rejected,
            "missing_interior_body_errors": missing_interior_body_errors,
            "image_above_stderr": image_result.stderr[-1200:],
            "text_above_stderr": text_result.stderr[-1200:],
            "cover_without_subtitle_stdout": cover_result.stdout[-1200:],
            "cover_without_subtitle_stderr": cover_result.stderr[-1200:],
        }, ensure_ascii=False, indent=2))
        return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
