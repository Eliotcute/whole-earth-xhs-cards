#!/usr/bin/env python3
"""Regression tests for mixed Chinese/Latin wrapping and annotation routing."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

from PIL import Image, ImageDraw

import render_card
from render_card import (
    ARIAL_UNICODE,
    CLOSING_PUNCTUATION,
    MUTED,
    PAPER,
    SONGTI,
    STHEITI_LIGHT,
    STHEITI_MEDIUM,
    contains_cjk,
    load_font,
    make_paper,
    wrap_chars,
)


def relative_luminance(color: tuple[int, int, int]) -> float:
    channels = []
    for value in color:
        channel = value / 255
        channels.append(channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast_ratio(foreground: tuple[int, int, int], background: tuple[int, int, int]) -> float:
    lighter, darker = sorted((relative_luminance(foreground), relative_luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def fallback_font_names(available_paths: set[str]) -> dict[str, tuple[str, str]]:
    def fake_exists(path):
        return str(path) in available_paths

    with mock.patch.object(render_card.Path, "exists", fake_exists):
        return {
            role: load_font(42, "serif", role).getname()
            for role in ("title", "body", "support")
        }


def main() -> int:
    image = Image.new("RGB", (900, 300), "white")
    draw = ImageDraw.Draw(image)
    font = load_font(42, "serif")
    lines = wrap_chars(draw, "让 WorkBuddy 动手操作浏览器，安装 agent-browser 后开始采集。", font, 330)
    latin_intact = any("WorkBuddy" in line for line in lines) and any("agent-browser" in line for line in lines)
    punctuation_valid = all(not line or line[0] not in CLOSING_PUNCTUATION for line in lines)
    width_valid = all(draw.textlength(line, font=font) <= 330 for line in lines)
    cjk_detected = contains_cjk("浏览器执行层") and not contains_cjk("TOOL NOTE")
    font_roles = {
        "title": load_font(42, "serif", "title").getname()[1],
        "body": load_font(42, "serif", "body").getname()[1],
        "support": load_font(42, "serif", "support").getname()[1],
    }
    font_roles_valid = not Path(SONGTI).is_file() or font_roles == {
        "title": "Bold",
        "body": "Regular",
        "support": "Light",
    }
    stheiti_font_names = fallback_font_names({STHEITI_MEDIUM, STHEITI_LIGHT})
    stheiti_simplified_faces_valid = stheiti_font_names == {
        "title": ("Heiti SC", "Medium"),
        "body": ("Heiti SC", "Light"),
        "support": ("Heiti SC", "Light"),
    }
    arial_font_names = fallback_font_names({ARIAL_UNICODE})
    arial_fallback_valid = all(
        name == ("Arial Unicode MS", "Regular") for name in arial_font_names.values()
    )
    body_contrast = contrast_ratio(MUTED, PAPER)
    contrast_valid = body_contrast >= 4.5
    original_serif_faces = render_card.SERIF_FACES
    try:
        render_card.SERIF_FACES = {role: [("/missing/cjk-font.ttf", 0)] for role in ("title", "body", "support")}
        try:
            load_font(42, "serif", "body")
            missing_cjk_font_rejected = False
        except RuntimeError:
            missing_cjk_font_rejected = True
    finally:
        render_card.SERIF_FACES = original_serif_faces
    paper = make_paper(500, 500, 1975)
    paper_reproducible = paper.tobytes() == make_paper(500, 500, 1975).tobytes()
    paper_pixels = paper.load()
    deviations = [
        max(abs(channel - base) for channel, base in zip(paper_pixels[x, y], PAPER))
        for y in range(paper.height)
        for x in range(paper.width)
    ]
    texture_visible_ratio = sum(value >= 2 for value in deviations) / len(deviations)
    texture_max_deviation = max(deviations)
    texture_valid = 0.01 <= texture_visible_ratio <= 0.08 and texture_max_deviation <= 10
    valid = (
        latin_intact and punctuation_valid and width_valid and cjk_detected
        and font_roles_valid and contrast_valid and missing_cjk_font_rejected
        and stheiti_simplified_faces_valid and arial_fallback_valid
        and paper_reproducible and texture_valid
    )
    print(json.dumps({
        "valid": valid,
        "lines": lines,
        "punctuation_valid": punctuation_valid,
        "width_valid": width_valid,
        "cjk_detected": cjk_detected,
        "font_roles": font_roles,
        "font_roles_valid": font_roles_valid,
        "stheiti_font_names": stheiti_font_names,
        "stheiti_simplified_faces_valid": stheiti_simplified_faces_valid,
        "arial_font_names": arial_font_names,
        "arial_fallback_valid": arial_fallback_valid,
        "body_contrast": body_contrast,
        "contrast_valid": contrast_valid,
        "missing_cjk_font_rejected": missing_cjk_font_rejected,
        "paper_reproducible": paper_reproducible,
        "texture_visible_ratio": texture_visible_ratio,
        "texture_max_deviation": texture_max_deviation,
        "texture_valid": texture_valid,
    }, ensure_ascii=False, indent=2))
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
