#!/usr/bin/env python3
"""Validate, render, and QA one or more independent card specifications."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from render_card import atomic_write_json
from validate_card_spec import load_bounded_json
from validate_stage_artifact import combined_digest


SCRIPT_DIR = Path(__file__).resolve().parent
REVIEW_CATEGORIES = (
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


def run(command: list[str]) -> None:
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode != 0:
        if result.stdout:
            print(result.stdout, file=sys.stderr, end="")
        if result.stderr:
            print(result.stderr, file=sys.stderr, end="")
        raise subprocess.CalledProcessError(result.returncode, command)


def review_path_for(output: Path) -> Path:
    return output.with_suffix(output.suffix + ".visual-review.json")


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_pending_review(path: Path, image: Path, preview: Path) -> None:
    payload = {
        "status": "pending",
        "image": str(image),
        "preview": str(preview),
        "image_sha256": file_digest(image),
        "preview_sha256": file_digest(preview),
        "scores": {category: None for category in REVIEW_CATEGORIES},
        "lowest_category": None,
        "revision_summary": "",
        "approved": False,
    }
    atomic_write_json(path, payload)


def validate_finalized_qa(qa_path: Path, spec: Path, image: Path, preview: Path, layout: Path) -> None:
    if not qa_path.exists():
        raise FileNotFoundError(f"pixel QA report is required before finalizing: {qa_path}")
    report = load_bounded_json(qa_path, "pixel QA report")
    if not isinstance(report, dict):
        raise ValueError(f"pixel QA report must contain a JSON object: {qa_path}")
    if report.get("valid") is not True:
        raise ValueError(f"pixel QA did not pass: {qa_path}")
    expected = {
        "spec_sha256": file_digest(spec),
        "image_sha256": file_digest(image),
        "preview_sha256": file_digest(preview),
        "layout_sha256": file_digest(layout),
    }
    for field, digest in expected.items():
        if report.get(field) != digest:
            raise ValueError(f"pixel QA is stale or belongs to different inputs: {field}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--finalize", action="store_true")
    parser.add_argument("--legacy-v0.6", dest="legacy_v0_6", action="store_true")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("cards", nargs="+")
    args = parser.parse_args()
    finalize = args.finalize
    legacy = args.legacy_v0_6

    specs = [Path(name).resolve() for name in args.cards]
    python = sys.executable
    resolved_outputs: list[Path] = []
    for spec in specs:
        validate_command = [python, str(SCRIPT_DIR / "validate_card_spec.py")]
        if legacy:
            validate_command.append("--legacy-v0.6")
        validate_command.append(str(spec))
        run(validate_command)
        cfg = load_bounded_json(spec, "CardSpec")
        output = Path(str(cfg["output"]))
        resolved_outputs.append(output if output.is_absolute() else (spec.parent / output).resolve())
    if len(set(resolved_outputs)) != len(resolved_outputs):
        raise ValueError("every card or variant must use a unique output path")
    if len(specs) > 1:
        run([python, str(SCRIPT_DIR / "validate_series.py"), *map(str, specs)])

    outputs: list[dict[str, str]] = []
    for spec in specs:
        cfg = load_bounded_json(spec, "CardSpec")
        output = Path(str(cfg["output"]))
        output = output if output.is_absolute() else (spec.parent / output).resolve()
        preview = output.with_name(output.stem + "-preview" + output.suffix)
        review = review_path_for(output)
        qa = output.with_suffix(output.suffix + ".qa.json")
        layout = output.with_suffix(output.suffix + ".layout.json")
        if finalize:
            if not output.exists() or not preview.exists() or not layout.exists():
                raise FileNotFoundError(f"render and inspect the card before finalizing: {output}")
            validate_finalized_qa(qa, spec, output, preview, layout)
            run([python, str(SCRIPT_DIR / "validate_visual_review.py"), str(review)])
        else:
            render_command = [python, str(SCRIPT_DIR / "render_card.py")]
            if legacy:
                render_command.append("--legacy-v0.6")
            render_command.append(str(spec))
            run(render_command)
            run([python, str(SCRIPT_DIR / "qa_card.py"), str(spec), str(output)])
            write_pending_review(review, output, preview)
        outputs.append(
            {
                "spec": str(spec),
                "image": str(output),
                "preview": str(preview),
                "qa": str(qa),
                "qa_sha256": file_digest(qa),
                "layout": str(layout),
                "layout_sha256": file_digest(layout),
                "visual_review": str(review),
                "visual_review_sha256": file_digest(review),
            }
        )

    manifest_path = args.manifest.expanduser().resolve() if args.manifest else specs[0].parent / "artifact-manifest.json"
    manifest = {
        "contract": "poem-artifact-manifest/v1",
        "status": "validated",
        "card_specs_digest": combined_digest(specs),
        "valid": True,
        "rendered": not finalize,
        "finalized": finalize,
        "pixel_valid": True,
        "deliverable": finalize,
        "visual_review_required": not finalize,
        "outputs": outputs,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(manifest_path, manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
