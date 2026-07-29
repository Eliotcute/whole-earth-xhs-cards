#!/usr/bin/env python3
"""Validate a single poetic-archive card specification before rendering."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from PIL import Image


PRIORITIES = {"aesthetic", "readable", "balanced"}
RENDER_MODES = {"final", "draft"}
CARD_ROLES = {"cover", "interior"}
LAYOUTS = {
    "archive-collage",
    "image-above",
    "quiet-specimen",
    "relief-emblem",
    "silhouette-field",
    "text-above",
    "text-led-note",
}
ASSET_TYPES = {"mono-photo", "ticket", "document", "relief-print", "silhouette", "color-block"}
COLOR_BLOCK_MOTIFS = {"solid", "sequence", "boundary", "index"}
SEMANTIC_ROLES = {
    "explain",
    "document",
    "locate",
    "sequence",
    "compare",
    "symbolize-specific-idea",
}
VAGUE_SEMANTIC_TERMS = {
    "atmosphere", "vintage", "beautiful", "poetic", "decorative", "decoration",
    "氛围", "营造氛围", "复古", "高级", "好看", "美观", "诗意", "装饰",
}
INVENTED_SOURCE_TERMS = {
    "invented", "fabricated", "fake", "fictional", "imaginary", "made up",
    "虚构", "伪造", "编造", "杜撰", "模型生成", "装饰性",
}
FORBIDDEN_OUTPUT_TERMS = {
    "comparison-board", "comparison", "contact-sheet", "diptych", "grid", "split-screen",
    "对比板", "拼版", "宫格", "双联", "合集",
}
CANVAS_PRESETS = {
    "xhs-portrait": (1242, 1660),
    "wechat-cover": (900, 383),
    "wechat-square-cover": (500, 500),
    "wechat-inline-portrait": (1080, 1440),
    "landscape-16x9": (1920, 1080),
    "portrait-9x16": (1080, 1920),
    "square-1x1": (1080, 1080),
    "portrait-4x5": (1080, 1350),
    "landscape-3x2": (1800, 1200),
    "custom": None,
}
MAX_CANVAS_EDGE = 4096
MAX_CANVAS_PIXELS = 8_500_000
MAX_SOURCE_IMAGE_EDGE = 8192
MAX_SOURCE_IMAGE_PIXELS = 32_000_000
MAX_JSON_BYTES = 1_000_000
CLUSTER_ZONES = {
    "upper-left", "upper-center", "upper-right",
    "middle-left", "center", "middle-right",
    "lower-left", "lower-center", "lower-right",
}
INTERSECTION_MODES = {"transparent-only", "controlled-overlap"}
CARD_SPEC_CONTRACT = "poem-card-spec/v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def load_bounded_json(path: Path, label: str = "JSON artifact", max_bytes: int = MAX_JSON_BYTES):
    with path.open("rb") as handle:
        payload = handle.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise ValueError(f"{label} exceeds the {max_bytes}-byte safety limit")
    try:
        return json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON: {exc}") from exc


def chinese_count(value: str) -> int:
    return sum("\u4e00" <= ch <= "\u9fff" for ch in value)


def normalized_copy(value: str) -> str:
    return "".join(str(value).split())


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_stage_ref(
    cfg: dict,
    base_dir: Path | None,
    ref_field: str,
    digest_field: str,
    expected_contract: str,
    errors: list[str],
) -> tuple[Path | None, dict | None]:
    raw_ref = str(cfg.get(ref_field, "")).strip()
    if not raw_ref:
        errors.append(f"{ref_field} is required for poem-card-spec/v1")
        return None, None
    if base_dir is None:
        errors.append(f"{ref_field} cannot be verified without the CardSpec base directory")
        return None, None
    path = Path(raw_ref)
    path = path if path.is_absolute() else base_dir / path
    if not path.is_file():
        errors.append(f"{ref_field} does not exist: {path}")
        return path, None
    try:
        upstream = load_bounded_json(path, ref_field)
    except (OSError, ValueError) as exc:
        errors.append(f"{ref_field} is not valid JSON: {exc}")
        return path, None
    expected_digest = file_digest(path)
    if str(cfg.get(digest_field, "")) != expected_digest:
        errors.append(f"{digest_field} is stale or belongs to a different {expected_contract}")
    if not isinstance(upstream, dict):
        errors.append(f"{ref_field} must contain a JSON object")
        return path, None
    if upstream.get("contract") != expected_contract:
        errors.append(f"{ref_field} must reference {expected_contract}")
    if upstream.get("status") != "validated":
        errors.append(f"{ref_field} must reference an artifact with status: validated")
    if expected_contract == "poem-design-plan/v1" and upstream.get("production_ready") is not True:
        errors.append("design_plan_ref must reference a production-ready DesignPlan")
    return path, upstream


def validate(
    cfg: dict,
    base_dir: Path | None = None,
    allow_legacy: bool = False,
    artifact_path: Path | None = None,
) -> list[str]:
    if not isinstance(cfg, dict):
        return ["CardSpec must contain a JSON object"]
    errors: list[str] = []
    for field in (
        "card_role", "source_ref", "source_excerpt", "card_claim",
        "canvas_preset", "width", "height", "priority", "layout",
        "cluster_zone", "title", "body", "output",
    ):
        if field not in cfg:
            errors.append(f"missing required field: {field}")

    contract = cfg.get("contract")
    if contract is None:
        if not allow_legacy:
            errors.append("legacy v0.6 CardSpec requires explicit --legacy-v0.6")
    else:
        if contract != CARD_SPEC_CONTRACT:
            errors.append(f"contract must be {CARD_SPEC_CONTRACT}")
        if cfg.get("status") != "validated":
            errors.append("poem-card-spec/v1 requires status: validated")
        for field in ("content_plan_digest", "design_plan_digest"):
            if not SHA256_RE.fullmatch(str(cfg.get(field, ""))):
                errors.append(f"{field} must be a lowercase SHA-256 digest for poem-card-spec/v1")
        if cfg.get("card_role") == "cover":
            title_digest = str(cfg.get("title_plan_digest", ""))
            if not SHA256_RE.fullmatch(title_digest):
                errors.append("cover specs require title_plan_digest as a lowercase SHA-256 digest")
        validate_stage_ref(
            cfg, base_dir, "content_plan_ref", "content_plan_digest",
            "poem-content-plan/v1", errors,
        )
        design_path, design_plan = validate_stage_ref(
            cfg, base_dir, "design_plan_ref", "design_plan_digest",
            "poem-design-plan/v1", errors,
        )
        if artifact_path is None:
            errors.append("poem-card-spec/v1 requires its artifact path for DesignPlan membership")
        elif design_path is not None and design_plan is not None:
            listed_specs = design_plan.get("card_specs")
            if not isinstance(listed_specs, list):
                errors.append("design_plan_ref.card_specs must be a list")
            else:
                resolved_specs = {
                    (Path(str(raw)) if Path(str(raw)).is_absolute() else design_path.parent / str(raw)).resolve()
                    for raw in listed_specs
                    if isinstance(raw, str) and raw.strip()
                }
                if artifact_path.resolve() not in resolved_specs:
                    errors.append("CardSpec is not listed in design_plan_ref.card_specs")
            selected_variant = design_plan.get("selected_variant")
            variant_id = cfg.get("design_variant_id")
            if not isinstance(variant_id, str) or not variant_id.strip():
                errors.append("design_variant_id is required for poem-card-spec/v1")
            elif variant_id != selected_variant:
                errors.append("design_variant_id must match design_plan_ref.selected_variant")
            variants = design_plan.get("variants")
            selected = next(
                (variant for variant in variants if isinstance(variant, dict) and variant.get("variant_id") == selected_variant),
                None,
            ) if isinstance(variants, list) else None
            allowed_layouts = selected.get("allowed_layouts") if isinstance(selected, dict) else None
            if not isinstance(allowed_layouts, list) or cfg.get("layout") not in allowed_layouts:
                errors.append("layout must be allowed by the selected DesignPlan variant")
        if cfg.get("card_role") == "cover":
            validate_stage_ref(
                cfg, base_dir, "title_plan_ref", "title_plan_digest",
                "poem-title-plan/v1", errors,
            )

    card_role = cfg.get("card_role")
    if card_role not in CARD_ROLES:
        errors.append(f"card_role must be one of {sorted(CARD_ROLES)}")

    source_ref = str(cfg.get("source_ref", "")).strip()
    source_excerpt = str(cfg.get("source_excerpt", "")).strip()
    card_claim = str(cfg.get("card_claim", "")).strip()
    if len(source_ref) < 3:
        errors.append("source_ref must identify the supplied or cited content source")
    if len(source_excerpt) < 8:
        errors.append("source_excerpt must quote or faithfully summarize at least 8 characters from the content source")
    if len(card_claim) < 4:
        errors.append("card_claim must state this card's exact claim")
    if card_claim and normalized_copy(card_claim) != normalized_copy(str(cfg.get("title", ""))):
        errors.append("card_claim must match title after whitespace and line-break normalization")

    priority = cfg.get("priority")
    if priority not in PRIORITIES:
        errors.append(f"priority must be one of {sorted(PRIORITIES)}")

    render_mode = cfg.get("render_mode", "final")
    if render_mode not in RENDER_MODES:
        errors.append(f"render_mode must be one of {sorted(RENDER_MODES)}")

    layout = cfg.get("layout")
    if layout not in LAYOUTS:
        errors.append(f"layout must be one of {sorted(LAYOUTS)}")

    cluster_zone = cfg.get("cluster_zone")
    if cluster_zone not in CLUSTER_ZONES:
        errors.append(f"cluster_zone must be one of {sorted(CLUSTER_ZONES)}")

    preset = cfg.get("canvas_preset")
    if preset not in CANVAS_PRESETS:
        errors.append(f"canvas_preset must be one of {sorted(CANVAS_PRESETS)}")
    raw_width = cfg.get("width", 0)
    raw_height = cfg.get("height", 0)
    dimensions_are_integers = (
        isinstance(raw_width, int) and not isinstance(raw_width, bool)
        and isinstance(raw_height, int) and not isinstance(raw_height, bool)
    )
    width = raw_width if dimensions_are_integers else 0
    height = raw_height if dimensions_are_integers else 0
    if not dimensions_are_integers:
        errors.append("width and height must be integers")
    elif width <= 0 or height <= 0:
        errors.append("width and height must be positive integers")
    elif width > MAX_CANVAS_EDGE or height > MAX_CANVAS_EDGE or width * height > MAX_CANVAS_PIXELS:
        errors.append(
            f"canvas exceeds safety limit: maximum edge {MAX_CANVAS_EDGE}px and "
            f"maximum area {MAX_CANVAS_PIXELS} pixels"
        )
    expected = CANVAS_PRESETS.get(preset)
    if expected and (width, height) != expected:
        errors.append(f"{preset} must use {expected[0]}x{expected[1]}; got {width}x{height}")

    assets = cfg.get("assets", [])
    if not isinstance(assets, list):
        errors.append("assets must be a list")
    else:
        if not assets and layout != "text-led-note":
            errors.append("text-only cards must use text-led-note so asset connectors are not rendered without an asset")
        if len(assets) > 2:
            errors.append("one card may use at most two visual assets")
        for index, asset in enumerate(assets[:2]):
            if not isinstance(asset, dict):
                errors.append(f"assets[{index}] must be an object")
                continue
            if asset.get("type") not in ASSET_TYPES:
                errors.append(f"assets[{index}].type must be one of {sorted(ASSET_TYPES)}")
            asset_type = asset.get("type")
            if asset_type == "color-block" and asset.get("motif", "solid") not in COLOR_BLOCK_MOTIFS:
                errors.append(f"assets[{index}].motif must be one of {sorted(COLOR_BLOCK_MOTIFS)}")
            role = str(asset.get("semantic_role", "")).strip()
            reason = str(asset.get("semantic_reason", "")).strip()
            if role not in SEMANTIC_ROLES:
                errors.append(f"assets[{index}].semantic_role must be one of {sorted(SEMANTIC_ROLES)}")
            if len(reason) < 8:
                errors.append(f"assets[{index}] requires a concrete semantic_reason of at least 8 characters")
            lowered_reason = reason.casefold()
            if any(term in lowered_reason for term in VAGUE_SEMANTIC_TERMS):
                errors.append(f"assets[{index}].semantic_reason is decorative or vague; bind it to the exact card claim")
            raw_path = asset.get("path")
            if render_mode == "final" and asset_type in {"mono-photo", "relief-print", "silhouette"} and not raw_path:
                errors.append(
                    f"assets[{index}] of type {asset_type} requires a supplied, generated, or licensed file path in final mode"
                )
            if raw_path and base_dir is not None:
                source_path = Path(str(raw_path))
                source_path = source_path if source_path.is_absolute() else base_dir / source_path
                if not source_path.exists():
                    errors.append(f"assets[{index}].path does not exist: {source_path}")
                elif not source_path.is_file():
                    errors.append(f"assets[{index}].path must be an image file: {source_path}")
                else:
                    try:
                        with Image.open(source_path) as source_image:
                            source_width, source_height = source_image.size
                        if (
                            source_width > MAX_SOURCE_IMAGE_EDGE
                            or source_height > MAX_SOURCE_IMAGE_EDGE
                            or source_width * source_height > MAX_SOURCE_IMAGE_PIXELS
                        ):
                            errors.append(
                                f"assets[{index}] exceeds source image safety limit: "
                                f"maximum edge {MAX_SOURCE_IMAGE_EDGE}px and "
                                f"maximum area {MAX_SOURCE_IMAGE_PIXELS} pixels"
                            )
                    except (OSError, Image.DecompressionBombError) as exc:
                        errors.append(f"assets[{index}].path is not a safe readable image: {exc}")
            if asset_type in {"ticket", "document"}:
                source_basis = str(asset.get("source_basis", "")).strip()
                if not source_basis:
                    errors.append(f"assets[{index}] of type {asset_type} requires source_basis")
                elif any(term in source_basis.casefold() for term in INVENTED_SOURCE_TERMS):
                    errors.append(f"assets[{index}].source_basis may not be invented or decorative")
                if not raw_path:
                    errors.append(f"assets[{index}] of type {asset_type} requires a real supplied/licensed source path")

    intersection = cfg.get("intentional_intersection")
    if intersection is not None:
        if not isinstance(intersection, dict):
            errors.append("intentional_intersection must be an object")
        else:
            mode = intersection.get("mode")
            if mode not in INTERSECTION_MODES:
                errors.append(f"intentional_intersection.mode must be one of {sorted(INTERSECTION_MODES)}")
            reason = str(intersection.get("reason", "")).strip()
            if len(reason) < 8:
                errors.append("intentional_intersection requires a concrete reason of at least 8 characters")
            if any(term in reason.casefold() for term in VAGUE_SEMANTIC_TERMS):
                errors.append("intentional_intersection.reason must explain a specific information or composition purpose")
            asset_indices = intersection.get("asset_indices", [])
            if not isinstance(asset_indices, list) or not asset_indices:
                errors.append("intentional_intersection.asset_indices must be a non-empty list")
            else:
                for asset_index in asset_indices:
                    if isinstance(asset_index, bool) or not isinstance(asset_index, int) or asset_index < 0 or asset_index >= len(assets):
                        errors.append(f"intentional_intersection asset index is invalid: {asset_index}")
            default_overlap = 0.0 if mode == "transparent-only" else 0.08
            max_opaque_overlap = intersection.get("max_opaque_overlap", default_overlap)
            if isinstance(max_opaque_overlap, bool) or not isinstance(max_opaque_overlap, (int, float)) or not 0 <= max_opaque_overlap <= 0.20:
                errors.append("intentional_intersection.max_opaque_overlap must be between 0 and 0.20")

    output = Path(str(cfg.get("output", "")))
    if output.suffix.casefold() != ".png":
        errors.append("output must be one independent .png file")
    if output.is_absolute():
        errors.append("output must be relative to the CardSpec directory")
    if ".." in output.parts:
        errors.append("output must not contain '..' path segments")
    if base_dir is not None:
        try:
            output_root = base_dir.resolve()
            resolved_output = (output_root / output).resolve()
            if not resolved_output.is_relative_to(output_root):
                errors.append("output must stay within the CardSpec directory")
        except (OSError, RuntimeError) as exc:
            errors.append(f"output path cannot be resolved safely: {exc}")
    lowered_output = output.stem.casefold()
    if any(term in lowered_output for term in FORBIDDEN_OUTPUT_TERMS):
        errors.append("output name suggests a board/grid/diptych; every card or variant must be independent")

    title_count = chinese_count(str(cfg.get("title", "")))
    body_count = chinese_count(str(cfg.get("body", "")))
    compact_canvas = min(width, height) <= 600
    if card_role == "cover":
        if not 8 <= title_count <= 18:
            errors.append("cover title/promise should contain roughly 8–18 Chinese characters")
        cover_lines = [line for line in str(cfg.get("title", "")).splitlines() if line.strip()]
        if preset == "xhs-portrait" and not 2 <= len(cover_lines) <= 4:
            errors.append("xhs cover title must declare two to four deliberate lines")
        if body_count and not 12 <= body_count <= 28:
            errors.append("optional cover subtitle should contain roughly 12–28 Chinese characters")
    else:
        if priority == "aesthetic" and not 12 <= title_count + body_count <= 60:
            errors.append("aesthetic mode should contain roughly 12–60 essential Chinese characters")
        if priority == "balanced":
            if not 8 <= title_count <= 32:
                errors.append("balanced title/core statement should contain roughly 8–32 Chinese characters")
            minimum_body = 10 if compact_canvas else 20
            if not minimum_body <= body_count <= 100:
                errors.append(f"balanced support copy should contain roughly {minimum_body}–100 Chinese characters for this canvas")
        if priority == "readable" and not 50 <= title_count + body_count <= 180:
            errors.append("readable mode should contain roughly 50–180 Chinese characters")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--legacy-v0.6", dest="legacy_v0_6", action="store_true")
    parser.add_argument("card")
    args = parser.parse_args()
    path = Path(args.card)
    try:
        cfg = load_bounded_json(path, "CardSpec")
    except (OSError, ValueError) as exc:
        print("INVALID")
        print(f"- {exc}")
        return 1
    errors = validate(cfg, path.resolve().parent, allow_legacy=args.legacy_v0_6, artifact_path=path.resolve())
    if errors:
        print("INVALID")
        for error in errors:
            print(f"- {error}")
        return 1
    print("VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
