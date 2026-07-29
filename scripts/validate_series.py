#!/usr/bin/env python3
"""Validate cross-card rhythm and consistency for a JSON card series."""

from __future__ import annotations

import sys
from pathlib import Path

from validate_card_spec import load_bounded_json


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: validate_series.py card-01.json card-02.json [...]", file=sys.stderr)
        return 2
    spec_paths = [Path(name).resolve() for name in sys.argv[1:]]
    try:
        cards = [load_bounded_json(path, "CardSpec") for path in spec_paths]
    except (OSError, ValueError) as exc:
        print("INVALID")
        print(f"- {exc}")
        return 1
    errors: list[str] = []
    output_owners: dict[Path, int] = {}
    for position, (spec_path, card) in enumerate(zip(spec_paths, cards), start=1):
        output = Path(str(card.get("output", "")))
        output = output if output.is_absolute() else (spec_path.parent / output).resolve()
        previous = output_owners.get(output)
        if previous is not None:
            errors.append(f"inputs {previous} and {position} reuse output path {output}")
        else:
            output_owners[output] = position
    grouped: dict[tuple, list[tuple[int, dict]]] = {}
    for position, card in enumerate(cards, start=1):
        series_id = card.get("series_id", "default-series")
        variant_id = card.get("variant_id") or (
            card.get("canvas_preset"), card.get("width"), card.get("height")
        )
        grouped.setdefault((series_id, str(variant_id)), []).append((position, card))

    for (series_id, variant_id), entries in grouped.items():
        entries.sort(key=lambda item: (item[1].get("card_number", item[0]), item[0]))
        variant_cards = [item[1] for item in entries]
        positions = [item[0] for item in entries]
        for index in range(1, len(variant_cards)):
            current, previous = variant_cards[index], variant_cards[index - 1]
            if (
                current.get("layout") == previous.get("layout")
                and current.get("cluster_zone")
                and current.get("cluster_zone") == previous.get("cluster_zone")
            ):
                errors.append(
                    f"series {series_id} variant {variant_id}: inputs {positions[index - 1]} and {positions[index]} "
                    f"repeat both layout {current.get('layout')} and cluster_zone {current.get('cluster_zone')}"
                )
        accents = {card.get("accent", "none") for card in variant_cards}
        papers = {card.get("paper", "pale-white-fiber") for card in variant_cards}
        canvases = {(card.get("canvas_preset"), card.get("width"), card.get("height")) for card in variant_cards}
        if len(accents) > 1:
            errors.append(f"series {series_id} variant {variant_id} uses inconsistent accents: {sorted(accents)}")
        if len(papers) > 1:
            errors.append(f"series {series_id} variant {variant_id} uses inconsistent paper directions: {sorted(papers)}")
        if len(canvases) > 1:
            errors.append(f"series {series_id} variant {variant_id} mixes canvases: {sorted(canvases)}")
    if errors:
        print("INVALID")
        for error in errors:
            print(f"- {error}")
        return 1
    print("VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
