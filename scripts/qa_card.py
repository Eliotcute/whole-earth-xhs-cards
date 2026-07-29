#!/usr/bin/env python3
"""Pixel and layout QA for a rendered poetic-archive card."""

from __future__ import annotations

import json
import hashlib
import math
import os
import sys
import tempfile
import unicodedata
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

from render_card import (
    ACCENTS, MUTED, canonical_asset_plan, get_asset, landscape_connector, make_paper,
    typography_sizes,
)
from validate_card_spec import MAX_CANVAS_EDGE, MAX_CANVAS_PIXELS, load_bounded_json, validate


EXPECTED_PAPER = (250, 250, 247)
EXPECTED_TEXT_COLORS = {"title": (17, 17, 15), "body": (86, 86, 80)}
BOX_LIMITS = {
    "title_boxes": 4,
    "body_boxes": 8,
    "micro_boxes": 16,
    "asset_boxes": 2,
    "asset_opaque_boxes": 2,
}
MAX_TEXT_SCAN_PIXELS = 2_000_000
MAX_LAYOUT_BYTES = 1_000_000


def atomic_replace(path: Path, writer) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o644)
        with os.fdopen(descriptor, "wb") as handle:
            writer(handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def open_bounded_image(path, mode):
    with Image.open(path) as source:
        width, height = source.size
        if width > MAX_CANVAS_EDGE or height > MAX_CANVAS_EDGE or width * height > MAX_CANVAS_PIXELS:
            raise ValueError(
                f"QA image exceeds safety limit: maximum edge {MAX_CANVAS_EDGE}px "
                f"and maximum area {MAX_CANVAS_PIXELS} pixels"
            )
        return source.convert(mode)


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def intersect(a, b):
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


def area(box):
    return max(0, box[2] - box[0]) * max(0, box[3] - box[1])


def contrast_ratio(rgb_a, rgb_b):
    def luminance(rgb):
        values = []
        for channel in rgb:
            value = channel / 255
            values.append(value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4)
        return 0.2126 * values[0] + 0.7152 * values[1] + 0.0722 * values[2]
    light, dark = sorted((luminance(rgb_a), luminance(rgb_b)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def read_rgb(value, field, errors):
    if not isinstance(value, list) or len(value) != 3 or any(type(channel) is not int for channel in value):
        errors.append(f"{field} must be an RGB integer triplet")
        return None
    rgb = tuple(value)
    if any(channel < 0 or channel > 255 for channel in rgb):
        errors.append(f"{field} channels must be between 0 and 255")
        return None
    return rgb


def read_box(value, field, image_size, errors):
    if not isinstance(value, list) or len(value) != 4 or any(type(coordinate) is not int for coordinate in value):
        errors.append(f"{field} must be an integer [left, top, right, bottom] box")
        return None
    left, top, right, bottom = value
    width, height = image_size
    if not (0 <= left < right <= width and 0 <= top < bottom <= height):
        errors.append(f"{field} must have positive area within the canvas")
        return None
    return left, top, right, bottom


def read_boxes(value, field, image_size, errors, required=False):
    if not isinstance(value, list):
        errors.append(f"{field} must be a list of boxes")
        return []
    if required and not value:
        errors.append(f"{field} must contain rendered text evidence")
    limit = BOX_LIMITS[field]
    if len(value) > limit:
        errors.append(f"{field} has too many boxes: {len(value)} > {limit}")
        return []
    boxes = []
    for index, raw_box in enumerate(value):
        box = read_box(raw_box, f"{field}[{index}]", image_size, errors)
        if box is not None:
            boxes.append(box)
    return boxes


def read_font_sizes(value, errors):
    if not isinstance(value, dict):
        errors.append("font_sizes must contain title, body, and micro sizes")
        return {"title": 0, "body": 0, "micro": 0}
    sizes = {}
    for field in ("title", "body", "micro"):
        size = value.get(field)
        if type(size) is not int or size <= 0 or size > MAX_CANVAS_EDGE:
            errors.append(f"font_sizes.{field} must be a positive bounded integer")
            sizes[field] = 0
        else:
            sizes[field] = size
    return sizes


def read_alpha_paths(value, image_path, asset_count, errors):
    if not isinstance(value, list) or len(value) != asset_count:
        errors.append("asset_alpha_paths must contain one path per rendered asset")
        return []
    paths = []
    for index, raw_path in enumerate(value):
        if not isinstance(raw_path, str) or not raw_path.strip():
            errors.append(f"asset_alpha_paths[{index}] must be a file path")
            continue
        path = Path(raw_path)
        if not path.is_absolute():
            path = image_path.parent / path
        expected = image_path.with_suffix(image_path.suffix + f".asset-{index}.alpha.png")
        try:
            resolved = path.resolve()
        except (OSError, RuntimeError) as exc:
            errors.append(f"asset_alpha_paths[{index}] cannot be resolved safely: {exc}")
            continue
        if resolved != expected:
            errors.append(f"asset_alpha_paths[{index}] does not match the rendered asset evidence path")
            continue
        if not resolved.is_file():
            errors.append(f"asset_alpha_paths[{index}] does not exist: {resolved}")
            continue
        paths.append(resolved)
    return paths


def read_asset_opacities(value, asset_count, errors):
    if not isinstance(value, list) or len(value) != asset_count:
        errors.append("asset_opacities must contain one value per rendered asset")
        return []
    opacities = []
    for index, opacity in enumerate(value):
        if type(opacity) is not int or not 0 <= opacity <= 255:
            errors.append(f"asset_opacities[{index}] must be an integer between zero and 255")
        else:
            opacities.append(opacity)
    return opacities


def minimum_text_evidence_area(text, font_size):
    visible_characters = sum(1 for character in str(text) if not character.isspace())
    return max(font_size * font_size, int(visible_characters * font_size * font_size * 0.15))


def print_fast_failure(errors):
    print(json.dumps({"valid": False, "errors": errors, "warnings": []}, ensure_ascii=False, indent=2))
    return 1


def box_color_evidence(im, boxes, expected, tolerance=18):
    pixels = im.load()
    matching = 0
    total = 0
    evidence = []
    for left, top, right, bottom in boxes:
        box_matching = 0
        min_x, min_y = right, bottom
        max_x, max_y = left - 1, top - 1
        for y in range(top, bottom):
            for x in range(left, right):
                total += 1
                if math.dist(pixels[x, y], expected) <= tolerance:
                    matching += 1
                    box_matching += 1
                    min_x, min_y = min(min_x, x), min(min_y, y)
                    max_x, max_y = max(max_x, x), max(max_y, y)
        box_area = max(1, (right - left) * (bottom - top))
        if box_matching:
            width_span = (max_x - min_x + 1) / (right - left)
            height_span = (max_y - min_y + 1) / (bottom - top)
        else:
            width_span = height_span = 0.0
        evidence.append({
            "coverage": box_matching / box_area,
            "width_span": width_span,
            "height_span": height_span,
        })
    return matching / max(1, total), evidence


def verify_alpha_evidence(cfg, spec_path, asset_boxes, opacities, alpha_images, accent, errors):
    assets = cfg.get("assets", [])
    seed = int(cfg.get("seed", 1975))
    render_mode = cfg.get("render_mode", "final")
    for index, (asset_box, opacity, actual_alpha) in enumerate(zip(asset_boxes, opacities, alpha_images)):
        width = asset_box[2] - asset_box[0]
        height = asset_box[3] - asset_box[1]
        try:
            expected_asset = get_asset(
                assets[index], spec_path, (width, height), accent, seed + index * 97, render_mode,
            )
            if opacity != 255:
                expected_asset.putalpha(
                    expected_asset.getchannel("A").point(lambda value: int(value * opacity / 255))
                )
            expected_alpha = expected_asset.getchannel("A")
        except (OSError, ValueError) as exc:
            errors.append(f"asset alpha evidence cannot be reproduced for asset {index}: {exc}")
            continue
        if ImageChops.difference(expected_alpha, actual_alpha).getbbox() is not None:
            errors.append(f"asset alpha evidence does not match the rendered source for asset {index}")


def point_in_boxes(x, y, boxes):
    return any(left <= x < right and top <= y < bottom for left, top, right, bottom in boxes)


def verify_asset_pixel_evidence(
    cfg, spec_path, im, asset_boxes, opacities, accent, title_px, excluded_boxes, errors,
):
    if not asset_boxes:
        return []

    seed = int(cfg.get("seed", 1975))
    render_mode = cfg.get("render_mode", "final")
    expected = make_paper(im.width, im.height, seed).convert("RGBA")
    records = []
    for index, (asset, asset_box, opacity) in enumerate(zip(cfg.get("assets", []), asset_boxes, opacities)):
        left, top, right, bottom = asset_box
        size = right - left, bottom - top
        try:
            rendered_asset = get_asset(
                asset, spec_path, size, accent, seed + index * 97, render_mode,
            )
            if opacity != 255:
                rendered_asset.putalpha(
                    rendered_asset.getchannel("A").point(lambda value: int(value * opacity / 255))
                )
        except (OSError, ValueError) as exc:
            errors.append(f"asset pixels cannot be reproduced for asset {index}: {exc}")
            continue
        before = expected.crop(asset_box).convert("RGB")
        expected.alpha_composite(rendered_asset, (left, top))
        records.append((index, asset_box, rendered_asset.getchannel("A"), before))

    connector = landscape_connector(cfg, title_px)
    if connector is not None:
        ImageDraw.Draw(expected, "RGBA").line(connector, fill=(*MUTED, 105), width=1)

    actual_pixels = im.load()
    metrics = []
    for index, asset_box, alpha, before in records:
        left, top, right, bottom = asset_box
        later_assets = [
            (later_box, later_alpha.load())
            for _, later_box, later_alpha, _ in records[index + 1:]
        ]
        after = expected.crop(asset_box).convert("RGB")
        alpha_pixels = alpha.load()
        before_pixels = before.load()
        after_pixels = after.load()
        sampled = 0
        matched = 0
        for local_y, y in enumerate(range(top, bottom)):
            for local_x, x in enumerate(range(left, right)):
                if alpha_pixels[local_x, local_y] < 32:
                    continue
                covered_by_later_asset = any(
                    later_box[0] <= x < later_box[2]
                    and later_box[1] <= y < later_box[3]
                    and later_alpha_pixels[x - later_box[0], y - later_box[1]] >= 32
                    for later_box, later_alpha_pixels in later_assets
                )
                if point_in_boxes(x, y, excluded_boxes) or covered_by_later_asset:
                    continue
                expected_pixel = after_pixels[local_x, local_y]
                if math.dist(expected_pixel, before_pixels[local_x, local_y]) <= 6:
                    continue
                sampled += 1
                if math.dist(actual_pixels[x, y], expected_pixel) <= 4:
                    matched += 1
        match_ratio = matched / max(1, sampled)
        metrics.append({"asset_index": index, "sampled_pixels": sampled, "match_ratio": match_ratio})
        if sampled < 64:
            errors.append(f"asset {index} has insufficient visible pixel evidence: {sampled} pixels")
        elif matched != sampled:
            errors.append(
                f"rendered asset pixels do not match asset {index}: {match_ratio:.2%} < 100.00%"
            )
    return metrics


def alpha_overlap_ratio(text_box, asset_box, alpha):
    intersection_box = (
        max(text_box[0], asset_box[0]),
        max(text_box[1], asset_box[1]),
        min(text_box[2], asset_box[2]),
        min(text_box[3], asset_box[3]),
    )
    if intersection_box[0] >= intersection_box[2] or intersection_box[1] >= intersection_box[3]:
        return 0.0
    local_box = (
        intersection_box[0] - asset_box[0],
        intersection_box[1] - asset_box[1],
        intersection_box[2] - asset_box[0],
        intersection_box[3] - asset_box[1],
    )
    crop = alpha.crop(local_box)
    opaque_pixels = sum(1 for value in crop.getdata() if value >= 32)
    return opaque_pixels / max(1, area(text_box))


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: qa_card.py card.json card.png", file=sys.stderr)
        return 2
    spec_path = Path(sys.argv[1]).resolve()
    requested_image_path = Path(sys.argv[2])
    try:
        cfg = load_bounded_json(spec_path, "CardSpec")
    except (OSError, ValueError) as exc:
        return print_fast_failure([str(exc)])
    errors = validate(cfg, spec_path.parent, allow_legacy=True, artifact_path=spec_path)
    if not isinstance(cfg, dict):
        return print_fast_failure(errors)
    warnings = []
    raw_output = Path(str(cfg.get("output", "")))
    if raw_output.is_absolute() or ".." in raw_output.parts:
        errors.append("CardSpec output must be a relative path without '..'")
        expected_output = spec_path.parent / raw_output.name
    else:
        expected_output = (spec_path.parent / raw_output).resolve()
        if not expected_output.is_relative_to(spec_path.parent):
            errors.append("CardSpec output must stay within the CardSpec directory")
    image_path = requested_image_path.resolve()
    if image_path != expected_output:
        errors.append(f"image path does not match CardSpec output: {requested_image_path} != {expected_output}")
    if errors:
        return print_fast_failure(errors)

    meta_path = image_path.with_suffix(image_path.suffix + ".layout.json")
    try:
        im = open_bounded_image(image_path, "RGB")
        meta = load_bounded_json(meta_path, "layout metadata", MAX_LAYOUT_BYTES)
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        return print_fast_failure([str(exc)])
    if not isinstance(meta, dict):
        return print_fast_failure(["layout metadata must contain a JSON object"])
    if im.size != (cfg["width"], cfg["height"]):
        errors.append(f"wrong dimensions: {im.size}, expected {(cfg['width'], cfg['height'])}")
    raw_asset_count = meta.get("asset_count")
    if type(raw_asset_count) is not int or not 0 <= raw_asset_count <= 2:
        errors.append("asset_count must be an integer between zero and two")
        asset_count = 0
    else:
        asset_count = raw_asset_count
    if asset_count != len(cfg.get("assets", [])):
        errors.append("asset_count does not match the CardSpec assets")
    raw_meta_output = Path(str(meta.get("output", "")))
    if not raw_meta_output.is_absolute():
        raw_meta_output = meta_path.parent / raw_meta_output
    try:
        if raw_meta_output.resolve() != image_path:
            errors.append("layout output does not match the reviewed image")
    except (OSError, RuntimeError) as exc:
        errors.append(f"layout output cannot be resolved safely: {exc}")
    for field in ("title", "body"):
        value = str(cfg.get(field, ""))
        if "\ufffd" in value or any(unicodedata.category(char) == "Cc" and char not in "\n\t" for char in value):
            errors.append(f"{field} contains replacement or control characters")

    safe = read_box(meta.get("safe_area"), "safe_area", im.size, errors)
    title_boxes = read_boxes(meta.get("title_boxes"), "title_boxes", im.size, errors, required=True)
    body_evidence_required = cfg.get("card_role") != "cover" or bool(str(cfg.get("body", "")).strip())
    body_boxes = read_boxes(
        meta.get("body_boxes"), "body_boxes", im.size, errors, required=body_evidence_required,
    )
    micro_boxes = read_boxes(meta.get("micro_boxes", []), "micro_boxes", im.size, errors)
    asset_boxes = read_boxes(meta.get("asset_boxes", []), "asset_boxes", im.size, errors)
    raw_opaque_boxes = meta.get("asset_opaque_boxes")
    if raw_opaque_boxes is None:
        raw_opaque_boxes = [list(box) for box in asset_boxes]
    opaque_boxes = read_boxes(raw_opaque_boxes, "asset_opaque_boxes", im.size, errors)
    if len(asset_boxes) != asset_count:
        errors.append("asset_boxes must contain one box per rendered asset")
    if len(opaque_boxes) != asset_count:
        errors.append("asset_opaque_boxes must contain one box per rendered asset")
    alpha_paths = read_alpha_paths(meta.get("asset_alpha_paths", []), image_path, asset_count, errors)
    asset_opacities = read_asset_opacities(meta.get("asset_opacities", []), asset_count, errors)
    font_sizes = read_font_sizes(meta.get("font_sizes"), errors)
    expected_title_px, expected_body_px, expected_micro_px = typography_sizes(cfg)
    expected_font_sizes = {
        "title": expected_title_px,
        "body": expected_body_px,
        "micro": expected_micro_px,
    }
    if font_sizes != expected_font_sizes:
        errors.append(
            f"font_sizes do not match deterministic renderer typography: "
            f"{font_sizes} != {expected_font_sizes}"
        )
    try:
        expected_asset_plan = canonical_asset_plan(cfg)
    except (OSError, ValueError) as exc:
        errors.append(f"asset geometry cannot be reproduced deterministically: {exc}")
        expected_asset_plan = []
    expected_asset_boxes = [item[0] for item in expected_asset_plan]
    expected_asset_opacities = [item[1] for item in expected_asset_plan]
    if asset_boxes != expected_asset_boxes:
        errors.append(
            f"asset geometry does not match deterministic renderer plan: "
            f"{asset_boxes} != {expected_asset_boxes}"
        )
    if asset_opacities != expected_asset_opacities:
        errors.append(
            f"asset opacities do not match deterministic renderer plan: "
            f"{asset_opacities} != {expected_asset_opacities}"
        )
    accent = read_rgb(meta.get("accent_rgb"), "accent_rgb", errors)
    paper_rgb = read_rgb(meta.get("paper_color"), "paper_color", errors)
    text_colors = meta.get("text_colors")
    if not isinstance(text_colors, dict):
        errors.append("text_colors must contain title and body RGB values")
        text_colors = {}
    title_rgb = read_rgb(text_colors.get("title"), "text_colors.title", errors)
    body_rgb = read_rgb(text_colors.get("body"), "text_colors.body", errors)
    for field, actual, expected in (
        ("paper_color", paper_rgb, EXPECTED_PAPER),
        ("text_colors.title", title_rgb, EXPECTED_TEXT_COLORS["title"]),
        ("text_colors.body", body_rgb, EXPECTED_TEXT_COLORS["body"]),
    ):
        if actual is not None and actual != expected:
            errors.append(f"unexpected {field}: {actual}, expected {expected}")
    expected_accent = ACCENTS.get(str(cfg.get("accent", "blue")), ACCENTS["blue"])
    if accent is not None and accent != expected_accent:
        errors.append(f"accent_rgb does not match the CardSpec accent: {accent} != {expected_accent}")

    for field, boxes, text_key in (
        ("title_boxes", title_boxes, "title"),
        ("body_boxes", body_boxes, "body"),
    ):
        if text_key == "body" and not body_evidence_required:
            continue
        font_size = font_sizes[text_key]
        minimum_side = max(4, font_size // 2)
        if any(box[2] - box[0] < minimum_side or box[3] - box[1] < minimum_side for box in boxes):
            errors.append(f"{field} contains implausibly small text evidence")
        if sum(area(box) for box in boxes) < minimum_text_evidence_area(cfg[text_key], font_size):
            errors.append(f"{field} area is too small for the declared text and font size")
    text_scan_pixels = sum(area(box) for box in title_boxes + body_boxes)
    scan_limit = min(MAX_TEXT_SCAN_PIXELS, int(im.width * im.height * 0.60))
    if text_scan_pixels > scan_limit:
        errors.append(f"text box scan area exceeds safety limit: {text_scan_pixels} > {scan_limit}")

    if safe is not None:
        for box in title_boxes + body_boxes:
            if box[0] < safe[0] or box[1] < safe[1] or box[2] > safe[2] or box[3] > safe[3]:
                errors.append(f"essential text outside safe area: {box}")
    essential = title_boxes + body_boxes
    for i, a in enumerate(essential):
        for b in essential[i + 1:]:
            if intersect(a, b) > 0:
                errors.append(f"essential text overlap: {a} / {b}")
    if errors:
        return print_fast_failure(errors)

    try:
        alpha_images = [open_bounded_image(path, "L") for path in alpha_paths]
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        return print_fast_failure([str(exc)])
    for index, (alpha_image, asset_box) in enumerate(zip(alpha_images, asset_boxes)):
        expected_alpha_size = asset_box[2] - asset_box[0], asset_box[3] - asset_box[1]
        if alpha_image.size != expected_alpha_size:
            errors.append(
                f"asset alpha dimensions do not match asset_boxes[{index}]: "
                f"{alpha_image.size} != {expected_alpha_size}"
            )
    if errors:
        return print_fast_failure(errors)
    verify_alpha_evidence(cfg, spec_path, asset_boxes, asset_opacities, alpha_images, accent, errors)
    if errors:
        return print_fast_failure(errors)
    asset_pixel_metrics = verify_asset_pixel_evidence(
        cfg, spec_path, im, asset_boxes, asset_opacities, accent, font_sizes["title"],
        title_boxes + body_boxes + micro_boxes, errors,
    )
    if errors:
        return print_fast_failure(errors)

    intersection_cfg = cfg.get("intentional_intersection") or {}
    permitted_assets = set(intersection_cfg.get("asset_indices", []))
    intersection_mode = intersection_cfg.get("mode")
    default_opaque_limit = 0.0 if intersection_mode == "transparent-only" else 0.08
    max_opaque_overlap = float(intersection_cfg.get("max_opaque_overlap", default_opaque_limit))
    intersection_metrics = []
    for text_box in essential:
        for asset_index, asset_box in enumerate(asset_boxes):
            layout_ratio = intersect(text_box, asset_box) / max(1, area(text_box))
            if asset_index < len(alpha_images):
                opaque_ratio = alpha_overlap_ratio(text_box, asset_box, alpha_images[asset_index])
            else:
                opaque_box = opaque_boxes[asset_index] if asset_index < len(opaque_boxes) else asset_box
                opaque_ratio = intersect(text_box, opaque_box) / max(1, area(text_box))
            if asset_index in permitted_assets:
                intersection_metrics.append({
                    "asset_index": asset_index,
                    "layout_overlap": layout_ratio,
                    "opaque_overlap": opaque_ratio,
                })
                if opaque_ratio > max_opaque_overlap:
                    errors.append(
                        f"intentional intersection exceeds opaque overlap limit: "
                        f"asset {asset_index}, {opaque_ratio:.2%} > {max_opaque_overlap:.2%}"
                    )
            elif layout_ratio > 0.04:
                errors.append(f"essential text materially collides with asset: {text_box} / {asset_box}")
    if intersection_cfg and not any(metric["layout_overlap"] > 0 for metric in intersection_metrics):
        warnings.append("intentional_intersection is declared but no essential text intersects the selected asset")
    pixel_access = im.load()
    accent_pixels = 0
    bright_pixels = 0
    for y in range(im.height):
        for x in range(im.width):
            pixel = pixel_access[x, y]
            accent_pixels += math.dist(pixel, accent) < 22
            bright_pixels += min(pixel) >= 238
    pixel_count = max(1, im.width * im.height)
    accent_ratio = accent_pixels / pixel_count
    if accent_ratio > 0.055:
        errors.append(f"accent coverage too high: {accent_ratio:.2%}")
    bright_ratio = bright_pixels / pixel_count
    if bright_ratio < 0.63:
        errors.append(f"insufficient quiet pale paper area: {bright_ratio:.2%}")
    short = min(im.size)
    minimum_title = max(28, int(short * 0.038))
    minimum_body = max(22, int(short * 0.027))
    if cfg.get("card_role") == "cover":
        minimum_title = max(minimum_title, int(68 * short / 1242))
    if font_sizes["title"] < minimum_title:
        errors.append(f"title font too small: {font_sizes['title']} < {minimum_title}")
    if font_sizes["body"] < minimum_body:
        errors.append(f"body font too small: {font_sizes['body']} < {minimum_body}")
    paper_for_contrast = paper_rgb or EXPECTED_PAPER
    title_for_contrast = title_rgb or EXPECTED_TEXT_COLORS["title"]
    body_for_contrast = body_rgb or EXPECTED_TEXT_COLORS["body"]
    title_contrast = contrast_ratio(title_for_contrast, paper_for_contrast)
    body_contrast = contrast_ratio(body_for_contrast, paper_for_contrast)
    essential_contrast = min(title_contrast, body_contrast)
    if essential_contrast < 4.5:
        errors.append(f"essential text contrast too low: {essential_contrast:.2f}:1")
    title_color_coverage, title_evidence = box_color_evidence(im, title_boxes, EXPECTED_TEXT_COLORS["title"])
    body_color_coverage, body_evidence = box_color_evidence(im, body_boxes, EXPECTED_TEXT_COLORS["body"])
    for field, boxes, evidence in (
        ("title", title_boxes, title_evidence),
        ("body", body_boxes, body_evidence),
    ):
        for index, (box, box_evidence) in enumerate(zip(boxes, evidence)):
            coverage = box_evidence["coverage"]
            if not 0.025 <= coverage <= 0.60:
                errors.append(
                    f"rendered {field} evidence has implausible ink coverage in box {index}: {coverage:.2%}"
                )
            box_width = box[2] - box[0]
            short_line = box_width <= font_sizes[field] * 2
            minimum_width_span = 0.35 if short_line else 0.45
            if box_evidence["width_span"] < minimum_width_span or box_evidence["height_span"] < 0.45:
                errors.append(
                    f"rendered {field} evidence does not span its declared box {index}: "
                    f"{box_evidence['width_span']:.2f}x{box_evidence['height_span']:.2f}"
                )
    if cfg.get("canvas_preset") == "portrait-9x16":
        ui_top = int(im.height * 0.10)
        ui_bottom = int(im.height * 0.88)
        for box in essential:
            if box[1] < ui_top or box[3] > ui_bottom:
                errors.append(f"essential text enters 9:16 interface exclusion zone: {box}")
    preview_width = 375
    preview_height = 500 if cfg.get("canvas_preset") == "xhs-portrait" else round(
        im.height * preview_width / im.width
    )
    thumbnail_title_px = font_sizes["title"] * preview_width / im.width
    thumbnail_body_px = font_sizes["body"] * preview_width / im.width
    minimum_thumbnail_title = 20 if cfg.get("card_role") == "cover" else 14
    if thumbnail_title_px < minimum_thumbnail_title:
        errors.append(
            f"title too small at thumbnail width: "
            f"{thumbnail_title_px:.1f}px < {minimum_thumbnail_title}px"
        )
    if thumbnail_body_px < 10:
        errors.append(f"body too small at thumbnail width: {thumbnail_body_px:.1f}px < 10px")
    if errors:
        return print_fast_failure(errors)

    preview = im.resize((preview_width, preview_height), Image.Resampling.LANCZOS)
    preview_path = image_path.with_name(image_path.stem + "-preview" + image_path.suffix)
    atomic_replace(preview_path, lambda handle: preview.save(handle, format="PNG", quality=94))
    result = {
        "valid": not errors,
        "spec_sha256": file_digest(spec_path),
        "image_sha256": file_digest(image_path),
        "preview_sha256": file_digest(preview_path),
        "layout_sha256": file_digest(meta_path),
        "errors": errors,
        "warnings": warnings,
        "metrics": {
            "accent_ratio": accent_ratio,
            "bright_ratio": bright_ratio,
            "title_contrast": title_contrast,
            "body_contrast": body_contrast,
            "essential_contrast": essential_contrast,
            "title_color_coverage": title_color_coverage,
            "body_color_coverage": body_color_coverage,
            "thumbnail_title_px": thumbnail_title_px,
            "thumbnail_body_px": thumbnail_body_px,
            "asset_pixel_evidence": asset_pixel_metrics,
            "intentional_intersections": intersection_metrics,
        },
        "preview": str(preview_path),
    }
    report_path = image_path.with_suffix(image_path.suffix + ".qa.json")
    encoded_result = json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8")
    atomic_replace(report_path, lambda handle: handle.write(encoded_result))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
