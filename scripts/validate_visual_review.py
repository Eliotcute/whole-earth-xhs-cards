#!/usr/bin/env python3
"""Validate the human/model-authored visual review required before delivery."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from validate_card_spec import load_bounded_json


CATEGORIES = (
    "semantic_specificity",
    "material_quality",
    "paper_tactility",
    "composition",
    "typography",
    "image_text_relationship",
    "negative_space",
    "series_rhythm",
    "mobile_readability",
    "provenance_restraint",
)


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate(review: dict) -> list[str]:
    if not isinstance(review, dict):
        return ["visual review must contain a JSON object"]
    errors: list[str] = []
    if review.get("status") != "approved":
        errors.append("status must be approved after visual inspection")
    for field, digest_field in (("image", "image_sha256"), ("preview", "preview_sha256")):
        raw_path = str(review.get(field, "")).strip()
        expected_digest = str(review.get(digest_field, "")).strip()
        if not raw_path or not expected_digest:
            errors.append(f"{field} and {digest_field} are required")
            continue
        path = Path(raw_path)
        if not path.exists():
            errors.append(f"reviewed {field} does not exist: {path}")
        elif file_digest(path) != expected_digest:
            errors.append(f"reviewed {field} changed after visual inspection")
    scores = review.get("scores")
    if not isinstance(scores, dict):
        return ["scores must be an object"]
    for category in CATEGORIES:
        score = scores.get(category)
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            errors.append(f"missing numeric score: {category}")
        elif not 0 <= float(score) <= 10:
            errors.append(f"score must be between 0 and 10: {category}")
        elif float(score) < 8:
            errors.append(f"visual gate failed: {category} is {score}, requires at least 8")
    numeric_scores = [float(scores[name]) for name in CATEGORIES if isinstance(scores.get(name), (int, float)) and not isinstance(scores.get(name), bool)]
    if len(numeric_scores) == len(CATEGORIES) and sum(numeric_scores) < 85:
        errors.append(f"visual gate failed: total is {sum(numeric_scores):.1f}, requires at least 85")
    if review.get("approved") is not True:
        errors.append("approved must be true after inspecting the full image and phone preview")
    lowest_category = review.get("lowest_category")
    if lowest_category not in CATEGORIES:
        errors.append("lowest_category must name one scored category")
    elif len(numeric_scores) == len(CATEGORIES):
        minimum_score = min(numeric_scores)
        if float(scores[lowest_category]) != minimum_score:
            errors.append("lowest_category must name a category with the actual minimum score")
    if len(str(review.get("revision_summary", "")).strip()) < 12:
        errors.append("revision_summary must state what was inspected or revised")
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: validate_visual_review.py card.png.visual-review.json", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    try:
        review = load_bounded_json(path, "visual review")
    except (OSError, ValueError) as exc:
        print("INVALID")
        print(f"- {exc}")
        return 1
    errors = validate(review)
    if errors:
        print("INVALID")
        for error in errors:
            print(f"- {error}")
        return 1
    total = sum(float(review["scores"][name]) for name in CATEGORIES)
    print(json.dumps({"valid": True, "total": total, "review": str(path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
