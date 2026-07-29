---
name: poemskills
description: "Route and coordinate PoemSkills editorial-card work from Chinese source material to publishable Xiaohongshu or WeChat cards. Use for PoemSkills、诗歌图文卡片、长文转卡片、完整卡组、直接出图、提示词或不知道该调用哪个 poem-* Skill. This is the thin entry point for poem-content, poem-title, poem-design, poem-render, and poem-review; it coordinates full workflows but does not duplicate their specialist rules."
---

# PoemSkills 导航与协调器

Route each request to one specialist. For a complete production request, coordinate the specialists in order and carry their versioned artifacts forward.

## Route the request

| User intent | Specialist | Expected artifact |
| --- | --- | --- |
| 提炼长文、逐卡文案、不要出图 | `$poem-content` | `ContentPlan` |
| 封面标题、发布标题、只改标题 | `$poem-title` | `TitlePlan` |
| 参考图、版式、配图、视觉提示词 | `$poem-design` | `DesignPlan`, then `CardSpec[]` |
| 一段可复制到 ChatGPT 的总 Prompt | `$poem-design` compatibility route | customized master prompt |
| 渲染、生成、导出 PNG | `$poem-render` | `ArtifactManifest` |
| 检查成品、手机可读性、评分、能否发布 | `$poem-review` | `ReviewReport` |

When the user explicitly names a `$poem-*` Skill, honor that route. Keep generic Xiaohongshu title work with the user's general title tool and generic image generation with the image tool; use these specialists only for PoemSkills card work.

`$name` is Codex invocation syntax. On hosts that invoke skills by bare name (for example Claude Code's `Skill` tool), read `$poem-content` as the skill `poem-content`; the `$` prefix carries no meaning there. The five specialist names are `poem-content`, `poem-title`, `poem-design`, `poem-render`, and `poem-review`.

## Coordinate complete work

For “直接做成卡片”, “完整卡组”, or equivalent end-to-end requests, execute:

```text
ContentPlan -> TitlePlan -> DesignPlan -> CardSpec[] -> ArtifactManifest -> ReviewReport
```

Read and follow, in order:

1. `skills/poem-content/SKILL.md`
2. `skills/poem-title/SKILL.md`
3. `skills/poem-design/SKILL.md`
4. `skills/poem-render/SKILL.md`
5. `skills/poem-review/SKILL.md`

Do not stop after strategy or prompts when the user asked for image files. Do not render raw long text before content and design artifacts exist.

Treat prompt requests as two distinct routes:

- For “给我一段可以复制到 ChatGPT 的总 Prompt”, read `references/master-prompt.md`, tailor its input block when source/context is available, and return one complete fenced prompt. Do not create a DesignPlan or CardSpec.
- For prompts tied to a specific card or full card set, complete content/title context as needed, select one DesignPlan, then return a separate text-free asset prompt and exact composition prompt for every requested card. Never collapse a series into one image prompt.

Read `references/stage-contracts.md` whenever two or more stages are involved. Preserve upstream digests so stale plans cannot silently drive new renders.

When the user asks only to inspect plans in chat, carry `status: provisional` inline artifacts through content, title, and design without writing files. Never describe provisional artifacts as validated or send them to render. File-backed validation becomes mandatory when production starts.

## Navigate the next step

- After `ContentPlan`: continue to title unless the user requested copy only.
- After `TitlePlan`: continue to `DesignPlan` unless the user requested title only.
- After `DesignPlan`: wait for a choice only when multiple unresolved variants materially differ; otherwise compile CardSpecs.
- After `CardSpec[]`: continue to render unless the user requested prompts/specs only.
- After `ArtifactManifest`: continue to review; generated files are not publishable yet.
- After a rejected `ReviewReport`: route the weakest category back to the owning specialist.

When the user says “直接做到可发布”, “自动完成”, or equivalent, treat that as authorization to revise the lowest category and repeat render, QA, and review without pausing. Stop after approval or three total review rounds. After three failed rounds, return the artifacts and the specific blocking gate; never label them publishable.

Feedback ownership:

- inaccurate claim or weak reader payoff -> `$poem-content`
- weak cover promise or title wrapping -> `$poem-title`
- generic asset, reference mismatch, repetitive layout -> `$poem-design`
- glyph, overflow, collision, export, or pixel failure -> `$poem-render`
- approval, release readiness, and iteration priority -> `$poem-review`

## Compatibility

Map former modes without exposing them as the main interface:

- `content-plan` -> `$poem-content`, then `$poem-title` when a cover is included
- `prompt-only` -> reusable master prompt or per-card prompts according to the two prompt routes above
- `cover-production` and `series-production` -> full coordinated workflow
- `style-sample` -> `$poem-design`, then render only the explicitly requested independent variants

Keep existing v0.6 card JSON compatible only through the explicit `scripts/run_pipeline.py --legacy-v0.6 ...` adapter. Never auto-downgrade a missing-contract spec to legacy. Every exported card remains independent; never combine variants or cards in one canvas.

If the user says a long source will be supplied but does not actually include or attach it, request the source before building a ContentPlan.
