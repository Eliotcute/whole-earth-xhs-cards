---
name: poem-title
description: "Create source-faithful cover promises and publishing copy packages for an existing PoemSkills ContentPlan. Use for PoemSkills 封面标题、封面文案、小红书正文与话题、公众号摘要、标题换行 or requests that explicitly invoke $poem-title. Do not use as a generic title-formula generator."
---

# Poem Title 标题与封面承诺

Turn a validated `ContentPlan` into exact cover language. Do not choose layout, font size, images, or coordinates.

Set `POEMSKILLS_ROOT` once before reading or running anything below. Run exactly one line matching the active host; each resolves the installed sibling `poemskills` symlink to the real repository root:

```bash
# Codex
POEMSKILLS_ROOT="$(cd -P "${CODEX_HOME:-$HOME/.codex}/skills/poemskills" && pwd)"
# Claude Code
POEMSKILLS_ROOT="$(cd -P "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills/poemskills" && pwd)"
```

Stop if the command fails or `test -f "$POEMSKILLS_ROOT/SKILL.md"` fails. Never infer the root from the current working directory or an unresolved `../../` path.

## Require content context

Prefer a `poem-content-plan/v1` artifact. When the user supplies only raw source material, complete `$poem-content` first rather than inventing a title from an unstructured excerpt.

## Write three candidates

Use three distinct source-backed angles:

1. `direct_value`: what the reader can understand, decide, or do;
2. `change_or_contrast`: the meaningful before/after or old/new distinction;
3. `specific_mechanism`: the concrete process, object, or evidence that makes the source distinctive.

Select one and state why it best matches the reader payoff. The cover is a promise for the next swipe, not a summary of every card.

## Constraints

- cover title: normally 8-18 Chinese characters;
- deliberate line breaks: two to four short lines for Xiaohongshu;
- optional subtitle: 12-28 Chinese characters;
- publishing title: no more than 20 Chinese characters including punctuation when practical;
- no unsupported numbers, outcomes, urgency, authority, or controversy;
- no empty phrases such as “建议收藏”, “真相来了”, or “颠覆认知”.

Optimize curiosity only after accuracy and specificity. Do not import a generic viral-title formula when it distorts the source.

## Deliver

Return:

1. three cover candidates;
2. the selected cover with exact line breaks;
3. optional subtitle;
4. three publishing-title candidates and one recommendation for publishing requests or complete workflows;
5. for validated production and complete workflows, a publication package containing Xiaohongshu title, body, tags, WeChat title and summary, plus concise alt text;
6. a `poem-title-plan/v1` JSON artifact following `$POEMSKILLS_ROOT/references/stage-contracts.md`.

Keep the publication package source-faithful. The body may create reading rhythm and a closing question, but must not introduce facts, outcomes, or authority absent from the ContentPlan. Tags describe the actual topic instead of generic traffic words. Alt text describes the card's visible content and purpose rather than repeating hashtags.

For a title-only planning reply, return only the requested candidates and selection as a provisional artifact. Do not force unrelated publishing copy into the chat response.

For planning-only chat work, return `status: provisional` inline and preserve the upstream reference without claiming file validation. For production, bind the artifact to the exact ContentPlan digest and validate it:

```bash
python3 "$POEMSKILLS_ROOT/scripts/validate_stage_artifact.py" title-plan.json --upstream content-plan.json
```

Route approved copy to `$poem-design`.
