#!/usr/bin/env python3
"""Render one publish-ready poetic-archive card from a validated JSON spec."""

from __future__ import annotations

import json
import math
import os
import random
import re
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from validate_card_spec import MAX_SOURCE_IMAGE_EDGE, MAX_SOURCE_IMAGE_PIXELS, load_bounded_json, validate


PAPER = (250, 250, 247)
FIBER = (226, 225, 218)
FIBER_DEEP = (206, 204, 194)
INK = (17, 17, 15)
MUTED = (86, 86, 80)
ACCENTS = {
    "none": INK,
    "black": INK,
    "blue": (61, 98, 112),
    "brick": (138, 59, 43),
    "red": (174, 75, 62),
    "olive": (102, 112, 68),
    "violet": (101, 86, 120),
}
SONGTI = "/System/Library/Fonts/Supplemental/Songti.ttc"
STHEITI_LIGHT = "/System/Library/Fonts/STHeiti Light.ttc"
STHEITI_MEDIUM = "/System/Library/Fonts/STHeiti Medium.ttc"
ARIAL_UNICODE = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"

# Songti.ttc bundles eight faces; index 0 is Songti SC Black, which is far too
# heavy for body copy. Select the weight explicitly so titles and body text can
# differ by weight instead of by size alone.
SERIF_FACES = {
    "title": [(SONGTI, 1), (STHEITI_MEDIUM, 1), (ARIAL_UNICODE, 0)],
    "body": [(SONGTI, 6), (STHEITI_LIGHT, 1), (ARIAL_UNICODE, 0)],
    "support": [(SONGTI, 3), (STHEITI_LIGHT, 1), (ARIAL_UNICODE, 0)],
}
SANS_FACES = {
    "title": [(STHEITI_MEDIUM, 0), (ARIAL_UNICODE, 0)],
    "body": [(STHEITI_LIGHT, 1), (ARIAL_UNICODE, 0)],
    "support": [(STHEITI_LIGHT, 1), (ARIAL_UNICODE, 0)],
}
MONO_FACES = {
    "title": [("/System/Library/Fonts/Supplemental/Courier New.ttf", 0), ("/System/Library/Fonts/Supplemental/Georgia.ttf", 0)],
    "body": [("/System/Library/Fonts/Supplemental/Courier New.ttf", 0), ("/System/Library/Fonts/Supplemental/Georgia.ttf", 0)],
    "support": [("/System/Library/Fonts/Supplemental/Courier New.ttf", 0), ("/System/Library/Fonts/Supplemental/Georgia.ttf", 0)],
}
CLOSING_PUNCTUATION = set("，。！？；：、）》】」』’”」％%!?;:,.])}")


def atomic_replace(path: Path, writer) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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


def atomic_save_png(image: Image.Image, path: Path, **options) -> None:
    atomic_replace(path, lambda handle: image.save(handle, format="PNG", **options))


def atomic_write_json(path: Path, payload: dict) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    atomic_replace(path, lambda handle: handle.write(encoded))


def load_font(size: int, family: str = "serif", weight: str = "body") -> ImageFont.FreeTypeFont:
    table = SERIF_FACES if family == "serif" else SANS_FACES if family == "sans" else MONO_FACES
    for candidate, index in table.get(weight, table["body"]):
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size=max(8, int(size)), index=index)
            except OSError:
                continue
    if family in {"serif", "sans"}:
        raise RuntimeError(
            f"No usable CJK-capable {family} font is installed; "
            "PoemSkills requires Songti SC, STHeiti, or Arial Unicode"
        )
    return ImageFont.load_default(size=max(8, int(size)))


def text_units(paragraph: str) -> list[str]:
    """Keep Latin identifiers intact while allowing natural CJK character wrapping."""
    return re.findall(r"[A-Za-z0-9][A-Za-z0-9_.:/+@-]*|[ \t]+|.", paragraph)


def split_oversized_unit(draw: ImageDraw.ImageDraw, unit: str, face: ImageFont.ImageFont, max_width: int) -> list[str]:
    fragments, current = [], ""
    for char in unit:
        trial = current + char
        if current and draw.textlength(trial, font=face) > max_width:
            fragments.append(current)
            current = char
        else:
            current = trial
    if current:
        fragments.append(current)
    return fragments


def wrap_chars(draw: ImageDraw.ImageDraw, text: str, face: ImageFont.ImageFont, max_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in str(text).splitlines() or [""]:
        if not paragraph:
            lines.append("")
            continue
        current = ""
        for unit in text_units(paragraph):
            trial = current + unit
            if current and draw.textlength(trial, font=face) > max_width:
                if unit in CLOSING_PUNCTUATION:
                    previous_units = [value for value in text_units(current.rstrip()) if value]
                    tail = previous_units.pop() if previous_units else ""
                    head = "".join(previous_units).rstrip()
                    if head:
                        lines.append(head)
                    current = tail + unit
                    if draw.textlength(current, font=face) > max_width:
                        fragments = split_oversized_unit(draw, current, face, max_width)
                        lines.extend(fragment.rstrip() for fragment in fragments[:-1])
                        current = fragments[-1]
                    continue
                lines.append(current.rstrip())
                current = unit.lstrip()
            else:
                current = trial
            if current and draw.textlength(current, font=face) > max_width:
                fragments = split_oversized_unit(draw, current, face, max_width)
                lines.extend(fragment.rstrip() for fragment in fragments[:-1])
                current = fragments[-1]
        if current:
            lines.append(current.rstrip())
    return lines


def contains_cjk(value: str) -> bool:
    return any("\u3400" <= char <= "\u9fff" for char in str(value))


def draw_text_block(draw, xy, text, face, fill, max_width, line_gap, max_lines=None):
    x, y = xy
    lines = wrap_chars(draw, text, face, max_width)
    if max_lines is not None and len(lines) > max_lines:
        raise ValueError(f"Text overflow: {len(lines)} lines exceeds {max_lines}")
    bbox = draw.textbbox((0, 0), "国Ag", font=face)
    line_h = bbox[3] - bbox[1] + line_gap
    boxes = []
    for line in lines:
        if line:
            box = draw.textbbox((x, y), line, font=face)
            draw.text((x, y), line, font=face, fill=fill)
            boxes.append(tuple(map(int, box)))
        y += line_h
    return y, boxes


def typography_sizes(cfg: dict) -> tuple[int, int, int]:
    width = int(cfg["width"])
    base = width / 1242
    priority = cfg.get("priority", "balanced")
    if cfg["card_role"] == "cover":
        title_px = int((88 if priority == "readable" else 82 if priority == "balanced" else 72) * max(0.72, base))
        body_px = int((44 if priority == "readable" else 40 if priority == "balanced" else 36) * max(0.72, base))
    else:
        title_px = int((58 if priority == "readable" else 52 if priority == "balanced" else 48) * max(0.72, base))
        body_px = int((38 if priority == "readable" else 34 if priority == "balanced" else 34) * max(0.72, base))
    micro_px = max(15, int(23 * max(0.68, base)))
    return title_px, body_px, micro_px


def build_copy_layer(
    cfg: dict, tx: int, ty: int, title_width: int, body_width: int,
    title_limit: int, body_limit: int, title_font=None, body_font=None,
) -> tuple[Image.Image, list[tuple[int, int, int, int]], list[tuple[int, int, int, int]]]:
    width, height = int(cfg["width"]), int(cfg["height"])
    short = min(width, height)
    margin = int(short * 0.062)
    title_px, body_px, _ = typography_sizes(cfg)
    title_font = title_font or load_font(title_px, "serif", "title")
    body_font = body_font or load_font(body_px, "serif", "body")
    title_gap = int(title_px * 0.52)
    body_gap = int(body_px * 0.62)
    inter_gap = max(int(body_px * 0.45), int(short * 0.012))
    available_top = int(height * 0.10) if cfg.get("canvas_preset") == "portrait-9x16" else margin
    available_bottom = int(height * 0.88) if cfg.get("canvas_preset") == "portrait-9x16" else height - margin

    def draw_on_layer(start_y):
        layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        layer_draw = ImageDraw.Draw(layer, "RGBA")
        _, measured_title = draw_text_block(
            layer_draw, (tx, start_y), cfg["title"], title_font, INK,
            title_width, title_gap, title_limit,
        )
        body_y = max([box[3] for box in measured_title] or [start_y]) + inter_gap
        _, measured_body = draw_text_block(
            layer_draw, (tx, body_y), cfg["body"], body_font, MUTED,
            body_width, body_gap, body_limit,
        )
        return layer, measured_title, measured_body

    text_layer, title_boxes, body_boxes = draw_on_layer(ty)
    essential = title_boxes + body_boxes
    if essential:
        min_y = min(box[1] for box in essential)
        max_y = max(box[3] for box in essential)
        shift_y = 0
        if max_y > available_bottom:
            shift_y = available_bottom - max_y
        if min_y + shift_y < available_top:
            shift_y += available_top - (min_y + shift_y)
        if shift_y:
            text_layer, title_boxes, body_boxes = draw_on_layer(ty + shift_y)
        final_essential = title_boxes + body_boxes
        final_max_y = max(box[3] for box in final_essential)
        if final_max_y > available_bottom:
            final_shift = available_bottom - final_max_y
            shifted_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            shifted_layer.alpha_composite(text_layer, (0, final_shift))
            text_layer = shifted_layer
            title_boxes = [(x0, y0 + final_shift, x1, y1 + final_shift) for x0, y0, x1, y1 in title_boxes]
            body_boxes = [(x0, y0 + final_shift, x1, y1 + final_shift) for x0, y0, x1, y1 in body_boxes]
    return text_layer, title_boxes, body_boxes


def make_paper(width: int, height: int, seed: int) -> Image.Image:
    rng = random.Random(seed)
    img = Image.new("RGB", (width, height), PAPER)
    d = ImageDraw.Draw(img, "RGBA")
    area_scale = max(1, width * height // 50000)
    # Papyrus fibers must be visible on close inspection while keeping texture
    # contrast under the ~4% ceiling in references/style-system.md.
    for _ in range(area_scale * 58):
        x = rng.randrange(width)
        y = rng.randrange(height)
        # Skewed length distribution: mostly short flecks, occasionally long
        # strands, so the weave never reads as a regular grid.
        length = int(rng.triangular(max(4, width // 220), max(26, width // 20), max(7, width // 120)))
        alpha = rng.randint(12, 28)
        drift = rng.choice([-2, -1, 0, 0, 1, 2])
        if rng.random() < 0.62:
            d.line((x, y, min(width, x + length), y + drift), fill=(*FIBER_DEEP, alpha), width=1)
        else:
            d.line((x, y, x + drift, min(height, y + length)), fill=(*FIBER_DEEP, alpha), width=1)
    # Sparse longer strands read as cross-woven papyrus rather than uniform noise.
    for _ in range(area_scale * 3):
        x = rng.randrange(width)
        y = rng.randrange(height)
        length = rng.randint(max(20, width // 20), max(40, width // 9))
        alpha = rng.randint(10, 20)
        if rng.random() < 0.5:
            d.line((x, y, min(width, x + length), y + rng.choice([-1, 0, 1])), fill=(*FIBER_DEEP, alpha), width=1)
        else:
            d.line((x, y, x + rng.choice([-1, 0, 1]), min(height, y + length)), fill=(*FIBER_DEEP, alpha), width=1)
    channels = img.split()
    bounded_channels = tuple(
        channel.point(lambda value, base=base: max(base - 10, min(base + 10, value)))
        for channel, base in zip(channels, PAPER)
    )
    return Image.merge("RGB", bounded_channels)


def asset_path(asset: dict, spec_path: Path) -> Path | None:
    raw = asset.get("path")
    if not raw:
        return None
    path = Path(raw)
    return path if path.is_absolute() else (spec_path.parent / path).resolve()


def open_source_image(path: Path, mode: str) -> Image.Image:
    with Image.open(path) as source:
        width, height = source.size
        if width > MAX_SOURCE_IMAGE_EDGE or height > MAX_SOURCE_IMAGE_EDGE or width * height > MAX_SOURCE_IMAGE_PIXELS:
            raise ValueError(
                f"Source image exceeds safety limit: maximum edge {MAX_SOURCE_IMAGE_EDGE}px "
                f"and maximum area {MAX_SOURCE_IMAGE_PIXELS} pixels"
            )
        return source.convert(mode)


def process_photo(path: Path, size: tuple[int, int], paper: tuple[int, int, int]) -> Image.Image:
    im = open_source_image(path, "RGB")
    im = ImageOps.fit(im, size, method=Image.Resampling.LANCZOS)
    im = ImageOps.grayscale(im)
    im = ImageEnhance.Contrast(im).enhance(1.18)
    im = ImageOps.colorize(im, black=(28, 28, 26), white=paper)
    return im


def process_cutout(path: Path, size: tuple[int, int], color=INK) -> Image.Image:
    im = open_source_image(path, "RGBA")
    if im.getextrema()[3] == (255, 255):
        gray = ImageOps.grayscale(im.convert("RGB"))
        gray = ImageOps.autocontrast(gray, cutoff=1)
        alpha = ImageEnhance.Contrast(ImageOps.invert(gray)).enhance(1.22)
        alpha = alpha.point(lambda value: 0 if value < 12 else value)
        content_box = alpha.getbbox()
        if content_box:
            alpha = alpha.crop(content_box)
        colored = Image.new("RGBA", im.size, (*color, 255))
        if content_box:
            colored = colored.crop(content_box)
        colored.putalpha(alpha)
        im = colored
    im.thumbnail(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    x = (size[0] - im.width) // 2
    y = (size[1] - im.height) // 2
    canvas.alpha_composite(im, (x, y))
    return canvas


def programmatic_asset(asset: dict, size: tuple[int, int], accent, seed: int) -> Image.Image:
    kind = asset.get("type", "relief-print")
    rng = random.Random(seed)
    w, h = size
    im = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(im, "RGBA")
    if kind == "color-block":
        left, top, right, bottom = w * 0.12, h * 0.14, w * 0.86, h * 0.82
        block = [
            (left, top + h * 0.012),
            (right - w * 0.008, top),
            (right, bottom - h * 0.015),
            (left + w * 0.01, bottom),
        ]
        d.polygon(block, fill=(*accent, 205))
        paper_cut = (*PAPER, 238)
        motif = asset.get("motif", "solid")
        if motif == "sequence":
            y = h * 0.48
            xs = [w * 0.27, w * 0.49, w * 0.71]
            d.line((xs[0], y, xs[-1], y), fill=paper_cut, width=max(2, w // 95))
            for index, x in enumerate(xs):
                radius = w * (0.055 if index < 2 else 0.075)
                d.rectangle((x - radius, y - radius, x + radius, y + radius), fill=paper_cut)
            d.polygon(
                [(w * 0.70, y - w * 0.11), (w * 0.80, y), (w * 0.70, y + w * 0.11)],
                fill=paper_cut,
            )
        elif motif == "boundary":
            gap_x = w * 0.54
            d.rectangle(
                (gap_x - w * 0.025, top + h * 0.10, gap_x + w * 0.025, bottom - h * 0.10),
                fill=paper_cut,
            )
            for index, length in enumerate((0.18, 0.27, 0.13)):
                yy = h * (0.34 + index * 0.15)
                d.line((gap_x - w * length, yy, gap_x - w * 0.06, yy), fill=paper_cut, width=max(2, w // 100))
                d.line((gap_x + w * 0.06, yy, gap_x + w * (length + 0.06), yy), fill=paper_cut, width=max(2, w // 100))
        elif motif == "index":
            for index, width_ratio in enumerate((0.46, 0.31, 0.40, 0.24)):
                yy = h * (0.31 + index * 0.12)
                d.rectangle((w * 0.27, yy, w * (0.27 + width_ratio), yy + h * 0.045), fill=paper_cut)
        for _ in range(12):
            yy = rng.uniform(top, bottom)
            x0 = rng.uniform(left, right - w * 0.08)
            d.line(
                (x0, yy, min(right, x0 + rng.uniform(w * 0.025, w * 0.10)), yy),
                fill=(*PAPER, 24),
                width=1,
            )
    elif kind == "silhouette":
        points = [(w * 0.08, h * 0.72), (w * 0.28, h * 0.43), (w * 0.46, h * 0.57), (w * 0.68, h * 0.22), (w * 0.92, h * 0.66)]
        d.line(points, fill=(*INK, 255), width=max(3, w // 35), joint="curve")
        for x, y in points:
            d.ellipse((x - w * 0.035, y - w * 0.035, x + w * 0.035, y + w * 0.035), fill=(*INK, 255))
    elif kind in {"ticket", "document"}:
        d.rounded_rectangle((w * 0.06, h * 0.1, w * 0.94, h * 0.88), radius=max(2, w // 60), fill=(243, 243, 238, 255), outline=(*INK, 150), width=max(1, w // 180))
        for row in range(5):
            yy = h * (0.25 + row * 0.105)
            d.line((w * 0.16, yy, w * (0.82 - row * 0.05), yy), fill=(*MUTED, 120), width=max(1, w // 220))
    else:
        stem_x = w * 0.48
        d.line((stem_x, h * 0.88, stem_x, h * 0.24), fill=(*INK, 255), width=max(4, w // 35))
        for index in range(7):
            yy = h * (0.75 - index * 0.075)
            side = -1 if index % 2 == 0 else 1
            cx = stem_x + side * w * (0.12 + rng.random() * 0.04)
            cy = yy
            rx, ry = w * 0.16, h * 0.07
            leaf = [(stem_x, yy), (cx - rx * 0.55, cy - ry * 0.25), (cx, cy - ry), (cx + rx * 0.62, cy), (cx, cy + ry), (cx - rx * 0.55, cy + ry * 0.2)]
            d.polygon(leaf, fill=(*INK, 255))
            for cut in range(3):
                offset = (cut - 1) * ry * 0.32
                d.line((stem_x, yy, cx + side * rx * 0.28, cy + offset), fill=(250, 250, 247, 230), width=max(1, w // 100))
        d.ellipse((stem_x - w * 0.08, h * 0.13, stem_x + w * 0.08, h * 0.29), fill=(*INK, 255))
    return im


def get_asset(asset: dict, spec_path: Path, size: tuple[int, int], accent, seed: int, render_mode: str, paper=PAPER) -> Image.Image:
    path = asset_path(asset, spec_path)
    kind = asset.get("type", "relief-print")
    if path and path.exists():
        if kind == "mono-photo":
            return process_photo(path, size, paper).convert("RGBA")
        return process_cutout(path, size)
    if kind == "color-block" or render_mode == "draft":
        return programmatic_asset(asset, size, accent, seed)
    raise ValueError(f"Final render requires a real asset path for {kind}: {asset.get('subject', 'unnamed asset')}")


def layout_anchor(zone: str, width: int, height: int, box_w: int, box_h: int, margin: int) -> tuple[int, int]:
    x_map = {"left": margin, "center": (width - box_w) // 2, "right": width - margin - box_w}
    y_map = {"upper": margin * 2, "middle": (height - box_h) // 2, "lower": height - margin * 2 - box_h}
    if zone == "center":
        return x_map["center"], y_map["middle"]
    parts = zone.split("-")
    return x_map[parts[-1]], y_map[parts[0]]


def opposite_side(zone: str, width: int, box_width: int, margin: int) -> int:
    """Place a text box opposite the declared focal cluster without overlap."""
    if zone.endswith("right"):
        return margin
    if zone.endswith("left"):
        return width - margin - box_width
    return margin


def place_two_columns(zone: str, width: int, margin: int, gap: int, asset_width: int, preferred_text_width: int):
    usable = width - margin * 2
    text_width = min(preferred_text_width, usable - asset_width - gap)
    if text_width <= 0:
        raise ValueError("Canvas is too narrow for the selected text and asset composition")
    if zone.endswith("left"):
        return width - margin - text_width, margin, text_width
    return margin, width - margin - asset_width, text_width


def landscape_connector(cfg: dict, title_px: int) -> tuple[int, int, int, int] | None:
    width, height = int(cfg["width"]), int(cfg["height"])
    layout = cfg.get("layout", "quiet-specimen")
    if width <= height or layout not in {"archive-collage", "relief-emblem", "quiet-specimen"}:
        return None
    short = min(width, height)
    margin = int(short * 0.062)
    gap = max(margin, int(short * 0.045))
    wide_short = height / width < 0.58
    asset_w = int(width * (0.25 if not wide_short else 0.20))
    asset_h = int(height * (0.50 if not wide_short else 0.56))
    preferred_text_w = int(width * 0.38)
    tx, ax, _ = place_two_columns(cfg.get("cluster_zone", "center"), width, margin, gap, asset_w, preferred_text_w)
    ay = layout_anchor(cfg.get("cluster_zone", "center"), width, height, asset_w, asset_h, margin)[1]
    ty = max(margin, int(height * 0.31))
    return ax + asset_w // 2, ay + asset_h // 2, tx, ty + title_px


def canonical_asset_plan(
    cfg: dict, text_above_bottom: int | None = None,
) -> list[tuple[tuple[int, int, int, int], int]]:
    width, height = int(cfg["width"]), int(cfg["height"])
    short = min(width, height)
    margin = int(short * 0.062)
    landscape = width > height
    wide_short = landscape and height / width < 0.58
    layout = cfg.get("layout", "quiet-specimen")
    zone = cfg.get("cluster_zone", "center")
    asset_count = len(cfg.get("assets", []))
    title_px, _, _ = typography_sizes(cfg)
    plan: list[tuple[tuple[int, int, int, int], int]] = []

    def add(x: int, y: int, box_width: int, box_height: int, opacity: int = 255) -> None:
        if len(plan) < asset_count:
            plan.append(((x, y, x + box_width, y + box_height), opacity))

    def portrait_position(box_width: int, box_height: int, default_right: bool = False):
        centered = zone == "center" or zone.endswith("center")
        on_right = zone.endswith("right") or (centered and default_right)
        x = width - margin - box_width if on_right else margin
        y = layout_anchor(zone, width, height, box_width, box_height, margin)[1]
        return x, y, on_right

    if layout in {"image-above", "text-above"}:
        cluster_width = int(width * (0.52 if landscape else 0.66))
        asset_width = int(width * (0.38 if landscape else 0.52))
        asset_height = int(height * (0.34 if landscape else 0.25))
        if zone.endswith("left"):
            text_x = margin
        elif zone.endswith("right"):
            text_x = width - margin - cluster_width
        else:
            text_x = (width - cluster_width) // 2
        asset_x = text_x + (cluster_width - asset_width) // 2
        vertical_gap = max(int(height * 0.055), int(title_px * 0.9))
        if layout == "image-above":
            asset_y = max(margin, int(height * (0.10 if landscape else 0.16)))
        else:
            if text_above_bottom is None:
                text_y = max(margin, int(height * (0.10 if landscape else 0.16)))
                _, title_boxes, body_boxes = build_copy_layer(
                    cfg, text_x, text_y, cluster_width, int(cluster_width * 0.92), 4, 7,
                )
                text_above_bottom = max(box[3] for box in title_boxes + body_boxes)
            asset_y = min(height - margin - asset_height, text_above_bottom + vertical_gap)
        add(asset_x, asset_y, asset_width, asset_height)
        add(
            asset_x + int(asset_width * 0.66), asset_y + int(asset_height * 0.66),
            int(asset_width * 0.32), int(asset_height * 0.30), 180,
        )
        return plan

    if landscape:
        gap = max(margin, int(short * 0.045))
        asset_width = int(width * (0.20 if wide_short else 0.25))
        asset_height = int(height * (0.56 if wide_short else 0.50))
        preferred_text_width = int(width * (0.43 if layout == "text-led-note" else 0.38))
        text_x, asset_x, _ = place_two_columns(
            zone, width, margin, gap, asset_width, preferred_text_width,
        )
        asset_y = layout_anchor(zone, width, height, asset_width, asset_height, margin)[1]
        text_y = max(margin, int(height * (0.25 if layout == "text-led-note" else 0.31)))
        if layout == "text-led-note":
            asset_width, asset_height = int(asset_width * 0.45), int(asset_height * 0.52)
            asset_x = width - margin - asset_width if text_x < width // 2 else margin
            asset_y = min(height - margin - asset_height, text_y + int(title_px * 1.2))
        add(asset_x, asset_y, asset_width, asset_height)
        add(
            asset_x + asset_width // 2, asset_y + asset_height // 2,
            asset_width // 2, asset_height // 2, 190,
        )
        return plan

    if layout == "archive-collage":
        asset_width, asset_height = int(width * 0.46), int(height * 0.37)
        asset_x, asset_y, _ = portrait_position(asset_width, asset_height)
        add(asset_x, asset_y, asset_width, asset_height)
        second_width, second_height = int(asset_width * 0.54), int(asset_height * 0.43)
        add(
            asset_x + int(asset_width * 0.06),
            min(height - margin - second_height, asset_y + int(asset_height * 0.78)),
            second_width, second_height, 225,
        )
    elif layout == "relief-emblem":
        asset_width, asset_height = int(width * 0.44), int(height * 0.35)
        asset_x, asset_y, _ = portrait_position(asset_width, asset_height, default_right=True)
        add(asset_x, asset_y, asset_width, asset_height)
        add(
            asset_x + int(asset_width * 0.60), asset_y + int(asset_height * 0.62),
            int(asset_width * 0.42), int(asset_height * 0.32), 190,
        )
    elif layout == "silhouette-field":
        asset_width, asset_height = int(width * 0.36), int(height * 0.29)
        asset_x, asset_y, _ = portrait_position(asset_width, asset_height, default_right=True)
        add(asset_x, asset_y, asset_width, asset_height)
        add(
            asset_x - int(asset_width * 0.10), asset_y + int(asset_height * 0.52),
            int(asset_width * 0.55), int(asset_height * 0.42), 145,
        )
    elif layout == "text-led-note":
        text_width = int(width * 0.58)
        text_x = margin * 2 if not zone.endswith("right") else width - margin * 2 - text_width
        text_y = max(
            margin * 3,
            int(height * (0.28 if zone.startswith("upper") else 0.36 if zone.startswith("middle") or zone == "center" else 0.48)),
        )
        asset_width, asset_height = int(width * 0.16), int(height * 0.12)
        asset_x = width - margin - asset_width if text_x < width // 2 else margin
        asset_y = min(height - margin - asset_height, text_y + int(height * 0.36))
        add(asset_x, asset_y, asset_width, asset_height)
        add(
            asset_x + asset_width // 2, asset_y + asset_height // 2,
            asset_width // 2, asset_height // 2, 175,
        )
    else:
        asset_width, asset_height = int(width * 0.29), int(height * 0.24)
        asset_x, asset_y, _ = portrait_position(asset_width, asset_height)
        add(asset_x, asset_y, asset_width, asset_height)
        add(
            asset_x + int(asset_width * 0.68), asset_y + int(asset_height * 0.62),
            int(asset_width * 0.38), int(asset_height * 0.34), 175,
        )
    return plan


def render(spec_path: Path, allow_legacy: bool = False) -> tuple[Path, Path]:
    cfg = load_bounded_json(spec_path, "CardSpec")
    validation_errors = validate(cfg, spec_path.parent, allow_legacy=allow_legacy, artifact_path=spec_path)
    if validation_errors:
        raise ValueError("Invalid card specification:\n- " + "\n- ".join(validation_errors))
    width, height = int(cfg["width"]), int(cfg["height"])
    short = min(width, height)
    seed = int(cfg.get("seed", 1975))
    accent = ACCENTS.get(str(cfg.get("accent", "blue")), ACCENTS["blue"])
    paper = make_paper(width, height, seed)
    img = paper.convert("RGBA")
    d = ImageDraw.Draw(img, "RGBA")
    margin = int(short * 0.062)
    safe = (margin, margin, width - margin, height - margin)
    landscape = width > height
    priority = cfg.get("priority", "balanced")
    render_mode = cfg.get("render_mode", "final")
    card_role = cfg["card_role"]
    title_px, body_px, micro_px = typography_sizes(cfg)
    title_font = load_font(title_px, "serif", "title")
    body_font = load_font(body_px, "serif", "body")
    micro_font = load_font(micro_px, "mono")
    title_boxes, body_boxes, micro_boxes = [], [], []
    asset_boxes, asset_opaque_boxes, asset_alpha_paths, asset_opacities = [], [], [], []
    layout = cfg.get("layout", "quiet-specimen")
    zone = cfg.get("cluster_zone", "center")
    assets = cfg.get("assets", [])

    wide_short = landscape and height / width < 0.58
    if landscape:
        cluster_w = int(width * (0.21 if wide_short else 0.24))
        cluster_h = int(height * (0.42 if wide_short else 0.46))
    else:
        cluster_w = int(width * (0.26 if height <= width * 1.18 else 0.30))
        cluster_h = int(height * (0.22 if height <= width * 1.18 else 0.20))
    ax, ay = layout_anchor(zone, width, height, cluster_w, cluster_h, margin)
    if cfg.get("canvas_preset") == "portrait-9x16":
        ui_top = int(height * 0.10)
        ui_bottom = int(height * 0.88)
        ay = min(max(ay, ui_top), ui_bottom - cluster_h)
    low_canvas = height <= 600
    compact_canvas = height <= 600 or (height <= width * 1.10 and short <= 600)
    gap = max(margin, int(short * 0.045))

    def draw_copy(tx, ty, title_width, body_width, title_limit=4, body_limit=8):
        nonlocal title_boxes, body_boxes
        text_layer, title_boxes, body_boxes = build_copy_layer(
            cfg, tx, ty, title_width, body_width, title_limit, body_limit,
            title_font=title_font, body_font=body_font,
        )
        img.alpha_composite(text_layer)
        return max([box[3] for box in title_boxes + body_boxes] or [ty])

    def paste_asset(index, box, opacity=255):
        if index >= len(assets):
            return
        x, y, w, h = box
        asset_im = get_asset(assets[index], spec_path, (w, h), accent, seed + index * 97, render_mode)
        if opacity != 255:
            asset_im.putalpha(asset_im.getchannel("A").point(lambda v: int(v * opacity / 255)))
        img.alpha_composite(asset_im, (x, y))
        asset_boxes.append((x, y, x + w, y + h))
        alpha_bbox = asset_im.getchannel("A").getbbox()
        if alpha_bbox:
            asset_opaque_boxes.append((
                x + alpha_bbox[0], y + alpha_bbox[1],
                x + alpha_bbox[2], y + alpha_bbox[3],
            ))
        else:
            asset_opaque_boxes.append((x, y, x, y))
        output = Path(cfg["output"])
        if not output.is_absolute():
            output = (spec_path.parent / output).resolve()
        alpha_path = output.with_suffix(output.suffix + f".asset-{index}.alpha.png")
        alpha_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_save_png(asset_im.getchannel("A"), alpha_path)
        asset_alpha_paths.append(str(alpha_path))
        asset_opacities.append(opacity)

    def paste_canonical_assets(text_above_bottom=None):
        for index, (asset_box, opacity) in enumerate(canonical_asset_plan(cfg, text_above_bottom)):
            left, top, right, bottom = asset_box
            paste_asset(index, (left, top, right - left, bottom - top), opacity)

    def portrait_asset_position(box_w: int, box_h: int, default_right: bool = False):
        centered = zone == "center" or zone.endswith("center")
        on_right = zone.endswith("right") or (centered and default_right)
        x = width - margin - box_w if on_right else margin
        y = layout_anchor(zone, width, height, box_w, box_h, margin)[1]
        return x, y, on_right

    if layout in {"image-above", "text-above"}:
        cluster_w = int(width * (0.52 if landscape else 0.66))
        asset_w = int(width * (0.38 if landscape else 0.52))
        asset_h = int(height * (0.34 if landscape else 0.25))
        if zone.endswith("left"):
            tx = margin
        elif zone.endswith("right"):
            tx = width - margin - cluster_w
        else:
            tx = (width - cluster_w) // 2
        ax = tx + (cluster_w - asset_w) // 2
        gap_y = max(int(height * 0.055), int(title_px * 0.9))
        if layout == "image-above":
            ay = max(margin, int(height * (0.10 if landscape else 0.16)))
            paste_canonical_assets()
            draw_copy(tx, ay + asset_h + gap_y, cluster_w, int(cluster_w * 0.92), 4, 7)
        else:
            ty = max(margin, int(height * (0.10 if landscape else 0.16)))
            text_bottom = draw_copy(tx, ty, cluster_w, int(cluster_w * 0.92), 4, 7)
            ay = min(height - margin - asset_h, text_bottom + gap_y)
            paste_canonical_assets(text_bottom)
    elif landscape:
        asset_w = int(width * (0.25 if not wide_short else 0.20))
        asset_h = int(height * (0.50 if not wide_short else 0.56))
        text_w = int(width * (0.43 if layout == "text-led-note" else 0.38))
        tx, ax, text_w = place_two_columns(zone, width, margin, gap, asset_w, text_w)
        ay = layout_anchor(zone, width, height, asset_w, asset_h, margin)[1]
        ty = max(margin, int(height * (0.25 if layout == "text-led-note" else 0.31)))
        if layout == "text-led-note":
            asset_w, asset_h = int(asset_w * 0.45), int(asset_h * 0.52)
            ax = width - margin - asset_w if tx < width // 2 else margin
            ay = min(height - margin - asset_h, ty + int(title_px * 1.2))
        paste_canonical_assets()
        draw_copy(tx, ty, text_w, int(text_w * 0.94), 4, 7)
        connector = landscape_connector(cfg, title_px)
        if connector is not None:
            d.line(connector, fill=(*MUTED, 105), width=1)
    elif layout == "archive-collage":
        asset_w, asset_h = int(width * 0.46), int(height * 0.37)
        ax, ay, asset_on_right = portrait_asset_position(asset_w, asset_h)
        text_w = int(width * 0.34)
        tx = margin if asset_on_right else width - margin - text_w
        ty = max(margin * 2, ay + int(asset_h * 0.17))
        paste_canonical_assets()
        draw_copy(tx, ty, text_w, int(text_w * 0.96), 4, 8)
        rule_y = min(height - margin, ty + int(asset_h * 0.66))
        d.line((tx, rule_y, tx + text_w, rule_y), fill=(*MUTED, 120), width=1)
    elif layout == "relief-emblem":
        asset_w, asset_h = int(width * 0.44), int(height * 0.35)
        ax, ay, asset_on_right = portrait_asset_position(asset_w, asset_h, default_right=True)
        text_w = int(width * 0.35)
        tx = margin if asset_on_right else width - margin - text_w
        ty = max(margin * 2, ay + int(asset_h * 0.22))
        paste_canonical_assets()
        draw_copy(tx, ty, text_w, int(text_w * 0.95), 4, 8)
        line_start = ax + asset_w if ax < tx else ax
        line_end = tx if ax < tx else tx + text_w
        d.line((line_start, ay + asset_h // 2, line_end, ty + title_px), fill=(*MUTED, 115), width=1)
    elif layout == "silhouette-field":
        asset_w, asset_h = int(width * 0.36), int(height * 0.29)
        ax, ay, asset_on_right = portrait_asset_position(asset_w, asset_h, default_right=True)
        text_w = int(width * 0.46)
        tx = margin if asset_on_right else width - margin - text_w
        ty = max(margin * 2, ay + int(asset_h * 0.10))
        paste_canonical_assets()
        draw_copy(tx, ty, text_w, int(text_w * 0.92), 4, 8)
        for index, (dx, dy) in enumerate(((0.10, 1.06), (0.52, 1.15), (0.92, 1.02))):
            cx, cy = ax + int(asset_w * dx), ay + int(asset_h * dy)
            radius = max(3, short // (270 + index * 30))
            d.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=(*accent, 235))
    elif layout == "text-led-note":
        text_w = int(width * 0.58)
        tx = margin * 2 if not zone.endswith("right") else width - margin * 2 - text_w
        ty = max(margin * 3, int(height * (0.28 if zone.startswith("upper") else 0.36 if zone.startswith("middle") or zone == "center" else 0.48)))
        draw_copy(tx, ty, text_w, int(text_w * 0.92), 4, 8)
        small_w, small_h = int(width * 0.16), int(height * 0.12)
        sx = width - margin - small_w if tx < width // 2 else margin
        sy = min(height - margin - small_h, ty + int(height * 0.36))
        paste_canonical_assets()
        slash_x = tx + int(text_w * 0.78)
        slash_y = min(height - margin * 2, ty + int(height * 0.36))
        d.line((slash_x, slash_y, slash_x + int(short * 0.035), slash_y - int(short * 0.075)), fill=(*INK, 155), width=1)
    else:  # quiet-specimen
        asset_w, asset_h = int(width * 0.29), int(height * 0.24)
        ax, ay, asset_on_right = portrait_asset_position(asset_w, asset_h)
        text_w = int(width * 0.43)
        tx = margin if asset_on_right else width - margin - text_w
        ty = max(margin * 2, ay + int(asset_h * 0.16))
        paste_canonical_assets()
        draw_copy(tx, ty, text_w, int(text_w * 0.94), 4, 8)
        line_start = ax + asset_w if ax < tx else ax
        line_end = tx if ax < tx else tx + text_w
        d.line((line_start, ay + int(asset_h * 0.58), line_end, ty + int(title_px * 0.70)), fill=(*MUTED, 100), width=1)

    annotations = [] if compact_canvas else cfg.get("annotations", [])
    bottom_annotation_y = max(margin, height - margin - micro_px)
    positions = [(margin, margin), (width - margin, bottom_annotation_y), (margin, bottom_annotation_y)]
    for index, annotation in enumerate(annotations[:3]):
        px, py = positions[index]
        annotation_face = load_font(micro_px, "sans" if contains_cjk(annotation) else "mono")
        if index == 1:
            annotation_width = d.textlength(str(annotation), font=annotation_face)
            px = max(margin, int(px - annotation_width))
        box = d.textbbox((px, py), str(annotation), font=annotation_face)
        d.text((px, py), str(annotation), font=annotation_face, fill=(*MUTED, 205))
        micro_boxes.append(tuple(map(int, box)))
    d.ellipse((margin, margin + micro_px * 1.8, margin + max(5, short // 190), margin + micro_px * 1.8 + max(5, short // 190)), fill=(*accent, 255))

    all_boxes = title_boxes + body_boxes + micro_boxes + asset_boxes
    for box in all_boxes:
        if box[0] < 0 or box[1] < 0 or box[2] > width or box[3] > height:
            raise ValueError(f"Element outside canvas: {box}")

    output = Path(cfg["output"])
    if not output.is_absolute():
        output = (spec_path.parent / output).resolve()
    atomic_save_png(img.convert("RGB"), output, quality=96)
    meta = {
        "canvas": {"width": width, "height": height, "preset": cfg["canvas_preset"]},
        "safe_area": safe,
        "priority": priority,
        "card_role": card_role,
        "layout": layout,
        "cluster_zone": zone,
        "asset_count": len(assets),
        "accent": cfg.get("accent", "blue"),
        "accent_rgb": accent,
        "paper_color": PAPER,
        "text_colors": {"title": INK, "body": MUTED},
        "font_sizes": {"title": title_px, "body": body_px, "micro": micro_px},
        "title_boxes": title_boxes,
        "body_boxes": body_boxes,
        "micro_boxes": micro_boxes,
        "asset_boxes": asset_boxes,
        "asset_opaque_boxes": asset_opaque_boxes,
        "asset_alpha_paths": asset_alpha_paths,
        "asset_opacities": asset_opacities,
        "output": str(output),
    }
    meta_path = output.with_suffix(output.suffix + ".layout.json")
    atomic_write_json(meta_path, meta)
    return output, meta_path


def main() -> int:
    legacy = "--legacy-v0.6" in sys.argv[1:]
    arguments = [value for value in sys.argv[1:] if value != "--legacy-v0.6"]
    if len(arguments) != 1:
        print("Usage: render_card.py [--legacy-v0.6] card.json", file=sys.stderr)
        return 2
    output, meta = render(Path(arguments[0]).resolve(), allow_legacy=legacy)
    print(output)
    print(meta)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
