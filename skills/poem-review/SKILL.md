---
name: poem-review
description: "Review PoemSkills card artifacts for source fidelity, semantic imagery, typography, composition, mobile readability, series rhythm, provenance, and release readiness. Use for PoemSkills 图片检查、卡片 QA、视觉评分、能否发布、迭代成品 or explicit $poem-review requests. Do not use for general code review."
---

# Poem Review 卡片审查

Decide whether rendered PoemSkills cards are publishable. Review first; revise files only when the user asks to fix or iterate, or when an end-to-end request explicitly says to complete the work to publishable status.

Set `POEMSKILLS_ROOT` once before reading or running anything below. Run exactly one line matching the active host; each resolves the installed sibling `poemskills` symlink to the real repository root:

```bash
# Codex
POEMSKILLS_ROOT="$(cd -P "${CODEX_HOME:-$HOME/.codex}/skills/poemskills" && pwd)"
# Claude Code
POEMSKILLS_ROOT="$(cd -P "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills/poemskills" && pwd)"
```

Stop if the command fails or `test -f "$POEMSKILLS_ROOT/SKILL.md"` fails. Never infer the root from the current working directory or an unresolved `../../` path.

## Required inputs

Use full-size PNGs, phone previews, CardSpecs, pixel-QA reports, and pending visual-review files. Read `$POEMSKILLS_ROOT/references/visual-quality-rubric.md` completely before scoring.

## Review order

1. Verify each card's claim against its source excerpt.
2. Verify every asset directly explains, documents, sequences, compares, locates, or specifically symbolizes that claim.
3. Inspect full-size output for material and typography defects.
4. Inspect the 375 px phone preview for two-second cover comprehension and readable interior support copy.
5. Compare adjacent cards for repeated mechanism, scale, and focal zone.
6. Score all ten rubric categories and identify the true lowest category.

Reject a card when any hard gate fails. Do not average away one irrelevant asset, unreadable card, stale QA report, or repeated template.

## Route revisions

- content accuracy or payoff -> `$poem-content`
- cover promise or exact title -> `$poem-title`
- asset relevance, layout, reference match, series rhythm -> `$poem-design`
- glyphs, line breaks, collisions, dimensions, export -> `$poem-render`

Revise the lowest category first when iteration is authorized. Re-run pixel QA and invalidate stale review data after any spec or image change.

For an authorized end-to-end run, repeat the owning-stage revision, render, QA, and review loop up to three total review rounds. Stop immediately on approval. If the third review still fails, report the exact hard gate and keep `approved` and `deliverable` false.

## Finalize

Approval requires every category at least 8/10, total at least 85/100, pixel QA valid, current hashes bound, and `approved: true`.

```bash
python3 "$POEMSKILLS_ROOT/scripts/run_pipeline.py" --finalize card-01.json card-02.json
```

Return a `poem-review-report/v1` artifact following `$POEMSKILLS_ROOT/references/stage-contracts.md`, plus concise findings, revisions, final paths, and any remaining risk.
