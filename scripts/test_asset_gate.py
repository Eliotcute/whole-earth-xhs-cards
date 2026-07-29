#!/usr/bin/env python3
"""Regression tests for final-vs-draft asset requirements."""

from __future__ import annotations

import json
import hashlib
import subprocess
import stat
import sys
import tempfile
from pathlib import Path

from PIL import Image

from validate_card_spec import validate
from render_card import get_asset, make_paper, open_source_image, programmatic_asset, render


SCRIPT_DIR = Path(__file__).resolve().parent


def qa_errors(result: subprocess.CompletedProcess[str]) -> list[str]:
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    return payload.get("errors", []) if isinstance(payload, dict) else []


def base_spec() -> dict:
    return {
        "card_role": "interior",
        "source_ref": "浏览器代理测试原文",
        "source_excerpt": "代理会打开来源、采集信息、截图并把结果填写到表单。",
        "card_claim": "浏览器代理开始执行网页任务",
        "canvas_preset": "xhs-portrait",
        "width": 1242,
        "height": 1660,
        "priority": "balanced",
        "layout": "relief-emblem",
        "cluster_zone": "middle-left",
        "title": "浏览器代理开始执行网页任务",
        "body": "它会打开来源、采集信息、截图、提取内容，再把结果填写进表单。",
        "assets": [{
            "type": "relief-print",
            "subject": "机械手操作浏览器",
            "semantic_role": "explain",
            "semantic_reason": "机械手直接解释代理开始执行浏览器任务",
            "path": None,
        }],
        "output": "card.png",
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="poemskills-asset-gate-") as raw_root:
        root = Path(raw_root)
        final_missing = base_spec()
        final_errors = validate(final_missing, root, allow_legacy=True)

        draft = base_spec()
        draft["render_mode"] = "draft"
        draft_errors = validate(draft, root, allow_legacy=True)

        supplied_path = root / "asset.png"
        Image.new("RGB", (80, 80), "white").save(supplied_path)
        supplied = base_spec()
        supplied["assets"][0]["path"] = str(supplied_path)
        supplied_errors = validate(supplied, root, allow_legacy=True)

        oversized_path = root / "oversized.png"
        Image.new("RGB", (8193, 10), "white").save(oversized_path)
        oversized = base_spec()
        oversized["assets"][0]["path"] = str(oversized_path)
        oversized_errors = validate(oversized, root, allow_legacy=True)
        try:
            open_source_image(oversized_path, "RGB")
            oversized_decode_rejected = False
        except ValueError:
            oversized_decode_rejected = True

        motif_errors = {}
        motif_digests = {}
        for motif in ("solid", "sequence", "boundary", "index"):
            color_block = base_spec()
            color_block["assets"][0].update({"type": "color-block", "path": None, "motif": motif})
            motif_errors[motif] = validate(color_block, root, allow_legacy=True)
            rendered = programmatic_asset(color_block["assets"][0], (240, 180), (61, 98, 112), 17)
            motif_digests[motif] = hashlib.sha256(rendered.tobytes()).hexdigest()

        misspelled = base_spec()
        misspelled["assets"][0].update({"type": "color-block", "path": None, "motif": "sequnce"})
        misspelled_errors = validate(misspelled, root, allow_legacy=True)

        render_root = root / "render-sidecars"
        render_root.mkdir()
        render_spec = base_spec()
        render_spec["render_mode"] = "draft"
        render_spec["assets"][0].update({"type": "color-block", "path": None, "motif": "sequence"})
        render_spec_path = render_root / "card.json"
        render_spec_path.write_text(json.dumps(render_spec, ensure_ascii=False, indent=2), encoding="utf-8")
        layout_sentinel = root / "layout-sentinel.txt"
        alpha_sentinel = root / "alpha-sentinel.txt"
        layout_sentinel.write_text("layout sentinel", encoding="utf-8")
        alpha_sentinel.write_text("alpha sentinel", encoding="utf-8")
        layout_path = render_root / "card.png.layout.json"
        alpha_path = render_root / "card.png.asset-0.alpha.png"
        layout_path.symlink_to(layout_sentinel)
        alpha_path.symlink_to(alpha_sentinel)
        render(render_spec_path, allow_legacy=True)
        render_modes = {
            path.name: stat.S_IMODE(path.stat().st_mode)
            for path in (render_root / "card.png", layout_path, alpha_path)
        }
        render_permissions_valid = all(mode == 0o644 for mode in render_modes.values())
        sidecars_safe = (
            layout_sentinel.read_text(encoding="utf-8") == "layout sentinel"
            and alpha_sentinel.read_text(encoding="utf-8") == "alpha sentinel"
            and layout_path.is_file() and not layout_path.is_symlink()
            and alpha_path.is_file() and not alpha_path.is_symlink()
        )

        baseline_qa = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "qa_card.py"), str(render_spec_path), str(render_root / "card.png")],
            text=True,
            capture_output=True,
        )
        layout = json.loads(layout_path.read_text(encoding="utf-8"))
        original_box = tuple(layout["asset_boxes"][0])
        forged_box = (100, 180, 180, 260)
        forged_size = forged_box[2] - forged_box[0], forged_box[3] - forged_box[1]
        forged_asset = get_asset(
            render_spec["assets"][0], render_spec_path, forged_size,
            tuple(layout["accent_rgb"]), 1975, "draft",
        )
        forged_image_path = render_root / "card.png"
        forged_image = Image.open(forged_image_path).convert("RGBA")
        paper = make_paper(render_spec["width"], render_spec["height"], 1975).convert("RGBA")
        forged_image.paste(paper.crop(original_box), original_box[:2])
        forged_image.alpha_composite(forged_asset, forged_box[:2])
        forged_image.convert("RGB").save(forged_image_path)
        forged_alpha = forged_asset.getchannel("A")
        forged_alpha.save(alpha_path)
        alpha_box = forged_alpha.getbbox()
        layout["asset_boxes"] = [list(forged_box)]
        layout["asset_opaque_boxes"] = [[
            forged_box[0] + alpha_box[0], forged_box[1] + alpha_box[1],
            forged_box[0] + alpha_box[2], forged_box[1] + alpha_box[3],
        ]]
        layout_path.write_text(json.dumps(layout, ensure_ascii=False, indent=2), encoding="utf-8")
        forged_geometry_qa = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "qa_card.py"), str(render_spec_path), str(forged_image_path)],
            text=True,
            capture_output=True,
        )
        forged_geometry_rejected = (
            forged_geometry_qa.returncode != 0
            and any("asset geometry" in error for error in qa_errors(forged_geometry_qa))
        )

        overlay_root = root / "transparent-overlay"
        overlay_root.mkdir()
        lower_source = overlay_root / "lower.png"
        upper_source = overlay_root / "upper.png"
        Image.new("RGBA", (360, 398), (17, 17, 15, 255)).save(lower_source)
        upper_asset = Image.new("RGBA", (136, 135), (0, 0, 0, 0))
        for x in range(116, 136):
            for y in range(135):
                upper_asset.putpixel((x, y), (17, 17, 15, 255))
        upper_asset.save(upper_source)
        overlay_spec = base_spec()
        overlay_spec.update({
            "layout": "quiet-specimen",
            "cluster_zone": "center",
            "output": "overlay.png",
            "assets": [
                {
                    "type": "relief-print",
                    "subject": "底层完整素材",
                    "semantic_role": "explain",
                    "semantic_reason": "提供必须保留的底层可见素材贡献",
                    "path": str(lower_source),
                },
                {
                    "type": "relief-print",
                    "subject": "上层透明素材",
                    "semantic_role": "symbolize-specific-idea",
                    "semantic_reason": "验证透明区域不能遮蔽底层素材证据",
                    "path": str(upper_source),
                },
            ],
        })
        overlay_spec_path = overlay_root / "overlay.json"
        overlay_spec_path.write_text(json.dumps(overlay_spec, ensure_ascii=False, indent=2), encoding="utf-8")
        overlay_image_path, overlay_layout_path = render(overlay_spec_path, allow_legacy=True)
        baseline_overlay_qa = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "qa_card.py"), str(overlay_spec_path), str(overlay_image_path)],
            text=True,
            capture_output=True,
        )
        overlay_layout = json.loads(overlay_layout_path.read_text(encoding="utf-8"))
        lower_box, upper_box = [tuple(box) for box in overlay_layout["asset_boxes"]]
        lower_alpha = Image.open(overlay_layout["asset_alpha_paths"][0]).convert("L")
        upper_alpha = Image.open(overlay_layout["asset_alpha_paths"][1]).convert("L")
        overlay_pixels = Image.open(overlay_image_path).convert("RGB")
        overlay_pixel_access = overlay_pixels.load()
        overlay_paper = make_paper(overlay_spec["width"], overlay_spec["height"], 1975)
        overlay_paper_access = overlay_paper.load()
        excluded_boxes = [
            tuple(box)
            for field in ("title_boxes", "body_boxes", "micro_boxes")
            for box in overlay_layout[field]
        ]
        erased_under_transparency = 0
        for y in range(max(lower_box[1], upper_box[1]), min(lower_box[3], upper_box[3])):
            for x in range(max(lower_box[0], upper_box[0]), min(lower_box[2], upper_box[2])):
                if any(left <= x < right and top <= y < bottom for left, top, right, bottom in excluded_boxes):
                    continue
                if lower_alpha.getpixel((x - lower_box[0], y - lower_box[1])) < 32:
                    continue
                if upper_alpha.getpixel((x - upper_box[0], y - upper_box[1])) != 0:
                    continue
                overlay_pixel_access[x, y] = overlay_paper_access[x, y]
                erased_under_transparency += 1
                if erased_under_transparency == 500:
                    break
            if erased_under_transparency == 500:
                break
        overlay_pixels.save(overlay_image_path)
        transparent_overlay_qa = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "qa_card.py"), str(overlay_spec_path), str(overlay_image_path)],
            text=True,
            capture_output=True,
        )
        transparent_overlay_erasure_rejected = (
            erased_under_transparency == 500
            and transparent_overlay_qa.returncode != 0
            and any(
                "rendered asset pixels do not match asset 0" in error
                for error in qa_errors(transparent_overlay_qa)
            )
        )

        motifs_valid = all(not errors for errors in motif_errors.values()) and len(set(motif_digests.values())) == 4
        valid = (
            bool(final_errors) and not draft_errors and not supplied_errors
            and bool(oversized_errors) and oversized_decode_rejected
            and motifs_valid and bool(misspelled_errors) and sidecars_safe
            and render_permissions_valid and baseline_qa.returncode == 0
            and forged_geometry_rejected
            and baseline_overlay_qa.returncode == 0
            and transparent_overlay_erasure_rejected
        )
        print(json.dumps({
            "valid": valid,
            "final_missing_rejected": bool(final_errors),
            "draft_allowed": not draft_errors,
            "supplied_allowed": not supplied_errors,
            "oversized_source_rejected": bool(oversized_errors),
            "oversized_decode_rejected": oversized_decode_rejected,
            "color_block_motifs_valid": motifs_valid,
            "color_block_outputs_distinct": len(set(motif_digests.values())) == 4,
            "misspelled_motif_rejected": bool(misspelled_errors),
            "render_sidecars_written_safely": sidecars_safe,
            "render_modes": {name: oct(mode) for name, mode in render_modes.items()},
            "render_permissions_valid": render_permissions_valid,
            "baseline_asset_geometry_valid": baseline_qa.returncode == 0,
            "forged_asset_geometry_rejected": forged_geometry_rejected,
            "forged_asset_geometry_errors": qa_errors(forged_geometry_qa),
            "baseline_transparent_overlay_valid": baseline_overlay_qa.returncode == 0,
            "transparent_overlay_pixels_erased": erased_under_transparency,
            "transparent_overlay_erasure_rejected": transparent_overlay_erasure_rejected,
            "transparent_overlay_errors": qa_errors(transparent_overlay_qa),
        }, ensure_ascii=False, indent=2))
        return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
