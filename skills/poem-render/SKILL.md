---
name: poem-render
description: "Render validated PoemSkills CardSpec JSON files into independent PNGs with deterministic Chinese typography, previews, layout manifests, and pixel QA. Use for PoemSkills 卡片渲染、生成 PNG、导出卡片 or explicit $poem-render requests. Do not use for generic image generation or raw long-text intake."
---

# Poem Render 卡片生成

Render approved CardSpecs. Own mechanical composition and export correctness, not editorial or art-direction decisions.

Set `POEMSKILLS_ROOT` once before reading or running anything below. Run exactly one line matching the active host; each resolves the installed sibling `poemskills` symlink to the real repository root:

```bash
# Codex
POEMSKILLS_ROOT="$(cd -P "${CODEX_HOME:-$HOME/.codex}/skills/poemskills" && pwd)"
# Claude Code
POEMSKILLS_ROOT="$(cd -P "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills/poemskills" && pwd)"
```

Stop if the command fails or `test -f "$POEMSKILLS_ROOT/SKILL.md"` fails. Never infer the root from the current working directory or an unresolved `../../` path.

## Input gate

Accept one or more validated CardSpec JSON files. Reject raw long text, an unapproved title, or a visual idea without specs; route those to `$poemskills` for coordination.

Accept legacy v0.6 specs only when the user explicitly requests the legacy adapter. New specs require `status: validated`, stage references, `contract`, `content_plan_digest`, `design_plan_digest`, and `title_plan_digest` for covers. Reject provisional or contractless specs by default.

## Render

Run:

```bash
python3 "$POEMSKILLS_ROOT/scripts/run_pipeline.py" card-01.json card-02.json
```

Legacy adapter:

```bash
python3 "$POEMSKILLS_ROOT/scripts/run_pipeline.py" --legacy-v0.6 old-card.json
```

This validates each spec, validates series rhythm, renders independent PNGs, creates phone previews and layout manifests, runs pixel QA, creates pending visual-review files, and writes `artifact-manifest.json` beside the first CardSpec. Use `--manifest PATH` to choose another destination. Successful stdout contains only the manifest JSON.

Never:

- combine cards or variants in one canvas;
- bake essential Chinese into a generated asset;
- silently change approved copy;
- bypass collision, overflow, safe-area, or output-path checks;
- describe a pending review as publishable.

If rendering reveals an editorial or asset problem, stop and route it to the owning specialist instead of patching the meaning inside the renderer.

## Deliver

Return an `ArtifactManifest` containing every spec, image, preview, pixel-QA report, layout manifest, and pending visual-review path. Include SHA-256 digests for QA, layout, and visual-review evidence. Follow `$POEMSKILLS_ROOT/references/stage-contracts.md` and bind the manifest to the exact CardSpec files.

Generated files are candidates, not deliverables. Route them to `$poem-review`.
