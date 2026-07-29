#!/usr/bin/env python3
"""Regression tests for declared image-text intersections."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

from render_card import canonical_asset_plan, get_asset, load_font, typography_sizes


SCRIPT_DIR = Path(__file__).resolve().parent


def qa_errors(result: subprocess.CompletedProcess[str]) -> list[str]:
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    return payload.get("errors", []) if isinstance(payload, dict) else []


def draw_lines(draw, lines, x, y, font, fill, gap):
    boxes = []
    for line in lines:
        box = tuple(map(int, draw.textbbox((x, y), line, font=font)))
        draw.text((x, y), line, font=font, fill=fill)
        boxes.append(box)
        y = box[3] + gap
    return boxes


def write_case(root: Path, name: str, asset_path: Path, mode: str, limit: float) -> tuple[Path, Path]:
    image_path = root / f"{name}.png"
    asset = {
        "type": "relief-print",
        "subject": "测试用透明素材",
        "semantic_role": "explain",
        "semantic_reason": "测试透明区域与不透明区域的碰撞差异",
        "path": str(asset_path),
    }
    spec = {
        "card_role": "interior",
        "source_ref": "受控相交测试原文",
        "source_excerpt": "文字只能进入素材透明区域，不能遮挡大面积不透明内容。",
        "card_claim": "受控相交必须保持正文清楚",
        "canvas_preset": "custom",
        "width": 400,
        "height": 400,
        "priority": "balanced",
        "layout": "quiet-specimen",
        "cluster_zone": "center",
        "title": "受控相交必须保持正文清楚",
        "body": "文字可以进入素材布局区域，但不能压住大面积不透明图像内容。",
        "assets": [asset],
        "intentional_intersection": {
            "mode": mode,
            "reason": "让文字穿过素材透明区域以形成受控图文关系",
            "asset_indices": [0],
            "max_opaque_overlap": limit,
        },
        "output": image_path.name,
    }
    spec_path = root / f"{name}.json"
    spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    image = Image.new("RGBA", (400, 400), (250, 250, 247, 255))
    asset_box, asset_opacity = canonical_asset_plan(spec)[0]
    asset_size = asset_box[2] - asset_box[0], asset_box[3] - asset_box[1]
    rendered_asset = get_asset(asset, spec_path, asset_size, (61, 98, 112), 1975, "final")
    image.alpha_composite(rendered_asset, asset_box[:2])
    image_draw = ImageDraw.Draw(image)
    title_px, body_px, micro_px = typography_sizes(spec)
    title_boxes = draw_lines(
        image_draw, ("受控相交", "保持清楚"), 45, 160,
        load_font(title_px, "serif", "title"), (17, 17, 15, 255), 8,
    )
    body_boxes = draw_lines(
        image_draw, ("文字可以进入素材", "布局区域但不能压住", "不透明图像内容"), 45, 265,
        load_font(body_px, "serif", "body"), (86, 86, 80, 255), 6,
    )
    image.convert("RGB").save(image_path)
    alpha_path = image_path.with_suffix(image_path.suffix + ".asset-0.alpha.png")
    rendered_asset.getchannel("A").save(alpha_path)
    meta = {
        "canvas": {"width": 400, "height": 400, "preset": "custom"},
        "safe_area": [24, 24, 376, 376],
        "priority": "balanced",
        "layout": "quiet-specimen",
        "cluster_zone": "center",
        "asset_count": 1,
        "accent": "blue",
        "accent_rgb": [61, 98, 112],
        "paper_color": [250, 250, 247],
        "text_colors": {"title": [17, 17, 15], "body": [86, 86, 80]},
        "font_sizes": {"title": title_px, "body": body_px, "micro": micro_px},
        "title_boxes": title_boxes,
        "body_boxes": body_boxes,
        "micro_boxes": [],
        "asset_boxes": [list(asset_box)],
        "asset_opaque_boxes": [[
            asset_box[0] + rendered_asset.getchannel("A").getbbox()[0],
            asset_box[1] + rendered_asset.getchannel("A").getbbox()[1],
            asset_box[0] + rendered_asset.getchannel("A").getbbox()[2],
            asset_box[1] + rendered_asset.getchannel("A").getbbox()[3],
        ]],
        "asset_alpha_paths": [str(alpha_path)],
        "asset_opacities": [asset_opacity],
        "output": str(image_path),
    }
    image_path.with_suffix(image_path.suffix + ".layout.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return spec_path, image_path


def main() -> int:
    python = sys.executable
    with tempfile.TemporaryDirectory(prefix="poemskills-intersection-") as raw_root:
        root = Path(raw_root)
        asset_path = root / "transparent-asset.png"
        asset = Image.new("RGBA", (240, 160), (0, 0, 0, 0))
        draw = ImageDraw.Draw(asset)
        draw.rectangle((0, 0, 19, 159), fill=(17, 17, 15, 255))
        asset.save(asset_path)

        transparent_spec, transparent_image = write_case(
            root, "transparent-pass", asset_path, "transparent-only", 0.0
        )
        validator = subprocess.run(
            [python, str(SCRIPT_DIR / "validate_card_spec.py"), "--legacy-v0.6", str(transparent_spec)],
            text=True, capture_output=True,
        )
        outside_preview = root / "outside-preview.txt"
        outside_report = root / "outside-report.txt"
        outside_preview.write_text("preview sentinel", encoding="utf-8")
        outside_report.write_text("report sentinel", encoding="utf-8")
        preview_path = transparent_image.with_name(transparent_image.stem + "-preview" + transparent_image.suffix)
        report_path = transparent_image.with_suffix(transparent_image.suffix + ".qa.json")
        preview_path.symlink_to(outside_preview)
        report_path.symlink_to(outside_report)
        transparent_result = subprocess.run(
            [python, str(SCRIPT_DIR / "qa_card.py"), str(transparent_spec), str(transparent_image)],
            text=True, capture_output=True,
        )
        safe_sidecar_writes = (
            outside_preview.read_text(encoding="utf-8") == "preview sentinel"
            and outside_report.read_text(encoding="utf-8") == "report sentinel"
            and preview_path.is_file() and not preview_path.is_symlink()
            and report_path.is_file() and not report_path.is_symlink()
        )
        transparent_meta_path = transparent_image.with_suffix(transparent_image.suffix + ".layout.json")
        transparent_meta = json.loads(transparent_meta_path.read_text(encoding="utf-8"))
        baseline_meta = copy.deepcopy(transparent_meta)
        valid_pixels = Image.open(transparent_image).copy()
        alpha_path = transparent_image.with_suffix(transparent_image.suffix + ".asset-0.alpha.png")
        valid_alpha = Image.open(alpha_path).copy()
        Image.new("L", valid_alpha.size, 0).save(alpha_path)
        forged_alpha_result = subprocess.run(
            [python, str(SCRIPT_DIR / "qa_card.py"), str(transparent_spec), str(transparent_image)],
            text=True, capture_output=True,
        )
        valid_alpha.save(alpha_path)
        erased_asset = valid_pixels.copy()
        erased_pixels = erased_asset.load()
        excluded_boxes = baseline_meta["title_boxes"] + baseline_meta["body_boxes"] + baseline_meta["micro_boxes"]
        asset_box = baseline_meta["asset_boxes"][0]
        for y in range(asset_box[1], asset_box[3]):
            for x in range(asset_box[0], asset_box[2]):
                if not any(left <= x < right and top <= y < bottom for left, top, right, bottom in excluded_boxes):
                    erased_pixels[x, y] = (250, 250, 247)
        erased_asset.save(transparent_image)
        erased_asset_result = subprocess.run(
            [python, str(SCRIPT_DIR / "qa_card.py"), str(transparent_spec), str(transparent_image)],
            text=True, capture_output=True,
        )
        valid_pixels.save(transparent_image)
        partially_erased_asset = valid_pixels.copy()
        partially_erased_pixels = partially_erased_asset.load()
        valid_alpha_pixels = valid_alpha.load()
        erased_pixel_count = 0
        for y in range(asset_box[1], asset_box[3]):
            for x in range(asset_box[0], asset_box[2]):
                local_x, local_y = x - asset_box[0], y - asset_box[1]
                if valid_alpha_pixels[local_x, local_y] < 32:
                    continue
                if any(left <= x < right and top <= y < bottom for left, top, right, bottom in excluded_boxes):
                    continue
                partially_erased_pixels[x, y] = (250, 250, 247)
                erased_pixel_count += 1
                if erased_pixel_count == 500:
                    break
            if erased_pixel_count == 500:
                break
        partially_erased_asset.save(transparent_image)
        partially_erased_asset_result = subprocess.run(
            [python, str(SCRIPT_DIR / "qa_card.py"), str(transparent_spec), str(transparent_image)],
            text=True, capture_output=True,
        )
        valid_pixels.save(transparent_image)
        spoof = Image.new("RGB", valid_pixels.size, "#FAFAF7")
        spoof.putpixel((120, 120), (17, 17, 15))
        spoof.putpixel((120, 170), (86, 86, 80))
        spoof.save(transparent_image)
        single_pixel_result = subprocess.run(
            [python, str(SCRIPT_DIR / "qa_card.py"), str(transparent_spec), str(transparent_image)],
            text=True, capture_output=True,
        )
        solid_blocks = valid_pixels.copy()
        solid_draw = ImageDraw.Draw(solid_blocks)
        for box in baseline_meta["title_boxes"]:
            solid_draw.rectangle(box, fill=(17, 17, 15))
        for box in baseline_meta["body_boxes"]:
            solid_draw.rectangle(box, fill=(86, 86, 80))
        solid_blocks.save(transparent_image)
        solid_block_result = subprocess.run(
            [python, str(SCRIPT_DIR / "qa_card.py"), str(transparent_spec), str(transparent_image)],
            text=True, capture_output=True,
        )
        valid_pixels.save(transparent_image)
        mismatched_image = root / "mismatched.png"
        valid_pixels.save(mismatched_image)
        mismatched_image.with_suffix(mismatched_image.suffix + ".layout.json").write_text(
            json.dumps(transparent_meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        mismatched_result = subprocess.run(
            [python, str(SCRIPT_DIR / "qa_card.py"), str(transparent_spec), str(mismatched_image)],
            text=True, capture_output=True,
        )
        mismatched_side_effect_free = not mismatched_image.with_name("mismatched-preview.png").exists() and not mismatched_image.with_suffix(
            mismatched_image.suffix + ".qa.json"
        ).exists()

        empty_boxes_meta = copy.deepcopy(baseline_meta)
        empty_boxes_meta["title_boxes"] = []
        empty_boxes_meta["body_boxes"] = []
        transparent_meta_path.write_text(json.dumps(empty_boxes_meta, ensure_ascii=False, indent=2), encoding="utf-8")
        empty_boxes_result = subprocess.run(
            [python, str(SCRIPT_DIR / "qa_card.py"), str(transparent_spec), str(transparent_image)],
            text=True, capture_output=True,
        )
        tiny_boxes_meta = copy.deepcopy(baseline_meta)
        tiny_boxes_meta["title_boxes"] = [[120, 120, 121, 121]]
        tiny_boxes_meta["body_boxes"] = [[120, 170, 121, 171]]
        transparent_meta_path.write_text(json.dumps(tiny_boxes_meta, ensure_ascii=False, indent=2), encoding="utf-8")
        tiny_boxes_result = subprocess.run(
            [python, str(SCRIPT_DIR / "qa_card.py"), str(transparent_spec), str(transparent_image)],
            text=True, capture_output=True,
        )
        oversized_boxes_meta = copy.deepcopy(baseline_meta)
        oversized_boxes_meta["title_boxes"] = [[0, 0, 1_000_000_000, 1_000_000_000]]
        transparent_meta_path.write_text(json.dumps(oversized_boxes_meta, ensure_ascii=False, indent=2), encoding="utf-8")
        oversized_boxes_result = subprocess.run(
            [python, str(SCRIPT_DIR / "qa_card.py"), str(transparent_spec), str(transparent_image)],
            text=True, capture_output=True,
            timeout=5,
        )

        transparent_meta = copy.deepcopy(baseline_meta)
        transparent_meta.pop("text_colors")
        transparent_meta_path.write_text(json.dumps(transparent_meta, ensure_ascii=False, indent=2), encoding="utf-8")
        missing_colors_result = subprocess.run(
            [python, str(SCRIPT_DIR / "qa_card.py"), str(transparent_spec), str(transparent_image)],
            text=True, capture_output=True,
        )
        transparent_meta["text_colors"] = {"title": "black", "body": [86, 86, 80]}
        transparent_meta_path.write_text(json.dumps(transparent_meta, ensure_ascii=False, indent=2), encoding="utf-8")
        malformed_colors_result = subprocess.run(
            [python, str(SCRIPT_DIR / "qa_card.py"), str(transparent_spec), str(transparent_image)],
            text=True, capture_output=True,
        )
        transparent_meta["text_colors"] = {"title": [18, 17, 15], "body": [86, 86, 80]}
        transparent_meta_path.write_text(json.dumps(transparent_meta, ensure_ascii=False, indent=2), encoding="utf-8")
        unexpected_colors_result = subprocess.run(
            [python, str(SCRIPT_DIR / "qa_card.py"), str(transparent_spec), str(transparent_image)],
            text=True, capture_output=True,
        )
        oversized_qa_image = root / "oversized-qa.png"
        Image.new("RGB", (4097, 10), "white").save(oversized_qa_image)
        oversized_qa_spec = copy.deepcopy(json.loads(transparent_spec.read_text(encoding="utf-8")))
        oversized_qa_spec["output"] = oversized_qa_image.name
        oversized_qa_spec_path = root / "oversized-qa.json"
        oversized_qa_spec_path.write_text(json.dumps(oversized_qa_spec, ensure_ascii=False, indent=2), encoding="utf-8")
        oversized_qa_result = subprocess.run(
            [python, str(SCRIPT_DIR / "qa_card.py"), str(oversized_qa_spec_path), str(oversized_qa_image)],
            text=True, capture_output=True,
        )

        opaque_source = root / "opaque-asset.png"
        Image.new("RGBA", (240, 160), (17, 17, 15, 255)).save(opaque_source)
        opaque_spec, opaque_image = write_case(
            root, "opaque-reject", opaque_source, "controlled-overlap", 0.03
        )
        opaque_result = subprocess.run(
            [python, str(SCRIPT_DIR / "qa_card.py"), str(opaque_spec), str(opaque_image)],
            text=True, capture_output=True,
        )

        checks = {
            "contract_validated": validator.returncode == 0,
            "transparent_region_passed": transparent_result.returncode == 0,
            "sidecar_symlinks_replaced_safely": safe_sidecar_writes,
            "forged_alpha_rejected": (
                forged_alpha_result.returncode != 0
                and any("alpha evidence does not match" in error for error in qa_errors(forged_alpha_result))
            ),
            "erased_asset_pixels_rejected": (
                erased_asset_result.returncode != 0
                and any("rendered asset pixels do not match" in error for error in qa_errors(erased_asset_result))
            ),
            "partial_asset_erasure_rejected": (
                erased_pixel_count == 500
                and partially_erased_asset_result.returncode != 0
                and any(
                    "rendered asset pixels do not match" in error
                    for error in qa_errors(partially_erased_asset_result)
                )
            ),
            "single_pixel_color_spoof_rejected": single_pixel_result.returncode != 0 and bool(qa_errors(single_pixel_result)),
            "solid_color_blocks_rejected": (
                solid_block_result.returncode != 0
                and any("implausible ink coverage" in error for error in qa_errors(solid_block_result))
            ),
            "mismatched_output_rejected": mismatched_result.returncode != 0 and bool(qa_errors(mismatched_result)),
            "mismatched_output_side_effect_free": mismatched_side_effect_free,
            "empty_text_boxes_rejected": empty_boxes_result.returncode != 0 and bool(qa_errors(empty_boxes_result)),
            "tiny_text_boxes_rejected": tiny_boxes_result.returncode != 0 and bool(qa_errors(tiny_boxes_result)),
            "oversized_text_boxes_rejected": oversized_boxes_result.returncode != 0 and bool(qa_errors(oversized_boxes_result)),
            "missing_text_colors_rejected": missing_colors_result.returncode != 0 and bool(qa_errors(missing_colors_result)),
            "malformed_text_colors_rejected": malformed_colors_result.returncode != 0 and bool(qa_errors(malformed_colors_result)),
            "unexpected_text_colors_rejected": unexpected_colors_result.returncode != 0 and bool(qa_errors(unexpected_colors_result)),
            "oversized_qa_image_rejected": (
                oversized_qa_result.returncode != 0
                and any("QA image exceeds safety limit" in error for error in qa_errors(oversized_qa_result))
            ),
            "opaque_region_rejected": (
                opaque_result.returncode != 0
                and any("intentional intersection exceeds" in error for error in qa_errors(opaque_result))
            ),
        }
        valid = all(checks.values())
        report = {
            "valid": valid,
            **checks,
            "erased_asset_errors": qa_errors(erased_asset_result),
            "solid_block_errors": qa_errors(solid_block_result),
            "transparent_output": transparent_result.stdout[-1200:],
            "opaque_output": opaque_result.stdout[-1200:],
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
