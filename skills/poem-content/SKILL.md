---
name: poem-content
description: "Extract a source-faithful PoemSkills content plan from long Chinese text, articles, transcripts, screenshots, or notes. Use for PoemSkills 卡片内容提炼、逐卡文案、内容摘要、读者收益、证据边界 or requests that explicitly invoke $poem-content. Do not use for generic writing or visual layout."
---

# Poem Content 内容提炼

Turn source material into one defensible editorial sequence. Do not design, render, or choose typography.

Set `POEMSKILLS_ROOT` once before reading or running anything below. Run exactly one line matching the active host; each resolves the installed sibling `poemskills` symlink to the real repository root:

```bash
# Codex
POEMSKILLS_ROOT="$(cd -P "${CODEX_HOME:-$HOME/.codex}/skills/poemskills" && pwd)"
# Claude Code
POEMSKILLS_ROOT="$(cd -P "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills/poemskills" && pwd)"
```

Stop if the command fails or `test -f "$POEMSKILLS_ROOT/SKILL.md"` fails. Never infer the root from the current working directory or an unresolved `../../` path.

Read `$POEMSKILLS_ROOT/references/content-first-workflow.md` completely before processing a long article, transcript, or screenshot with substantial text.

## Input gate

Separate each input as:

- `content_source`: facts, arguments, examples, names, and wording;
- `visual_reference`: appearance only, never a source of claims;
- `reusable_asset`: user-owned or authorized material.

If no source supports a claim, remove it. Ask at most three questions only when missing context changes the factual conclusion.

## Build the ContentPlan

Extract:

1. output scope: `cover-only`, `cover-plus-interiors`, or `interiors-only`;
2. topic in one factual sentence;
3. central change, tension, or question;
4. reader situation and payoff;
5. strongest source-backed evidence;
6. boundaries and facts that must not be invented;
7. desired reader action;
8. one short cover direction, not final cover copy;
9. one unique claim per interior card when the scope includes interiors.

Default to five interior cards when the user requests a set without a count. For `cover-only`, return no interior cards and continue to `$poem-title`. Use only roles supported by the source: `context`, `claim`, `mechanism`, `evidence`, `use`, or `source`.

Each card must contain:

- a standalone claim;
- a 12-28-character core sentence;
- normally 35-90 supporting Chinese characters;
- one source excerpt or faithful source summary;
- a reason the card exists in the sequence;
- an image decision with semantic role, or `none`.

No image is better than a generic image. Do not convert every paragraph into poetic fragments.

## Deliver

Return:

1. a concise readable editorial brief;
2. the ordered card script;
3. a `poem-content-plan/v1` JSON artifact following `$POEMSKILLS_ROOT/references/stage-contracts.md`.

For planning-only chat work, return the same structure inline with `status: provisional`; it may continue to title/design but cannot enter render. Write and validate a file-backed artifact when production will follow:

```bash
python3 "$POEMSKILLS_ROOT/scripts/validate_stage_artifact.py" content-plan.json --source source.txt
```

Do not produce final cover candidates, visual prompts, card specs, or image files. Route final cover wording to `$poem-title`.
