# PoemSkills 诗歌图文卡片

诗歌般克制，但仍把事情说清楚。PoemSkills 把中文长文提炼成可发布的小红书与公众号封面、文字卡片和主题配图，并用确定性排版与 QA 保证手机阅读。

## About

`PoemSkills` 是由[适之 Shizhi](https://github.com/Eliotcute)维护的本地 Codex Skill 套件。它不是自动写诗工具，也不是一个万能图片 Prompt；它是一条有明确阶段合同的中文编辑卡片生产线。

源码仓库：[`Eliotcute/PoemSkills`](https://github.com/Eliotcute/PoemSkills)

系统把“提炼内容、写标题、做设计、渲染图片、发布审查”拆成五个可以单独调用的 Skill。根入口只负责路由和完整流程协调，避免一次加载所有规则后出现模式混淆。

## 30 秒开始

安装后，在 Codex 里直接输入自然语言，不需要先写 JSON：

```text
使用 $poemskills，把下面长文做成一张封面和五张内页，直接执行到可发布。

内容：
【粘贴长文】
```

只需要一段拿去 ChatGPT 使用的总 Prompt：

```text
使用 $poemskills，根据下面的内容给我一段可复制到 ChatGPT 的完整 Prompt，不生成图片。

内容：
【粘贴长文】
```

第一种调用会自动走完内容、标题、设计、渲染和审查；审查不通过时优先修最低分项，最多三轮。第二种调用只交付一段完整 Prompt，不会生成 DesignPlan、CardSpec 或图片。

## Skill 架构

| 调用名 | 单一职责 | 主要产物 |
| --- | --- | --- |
| `$poemskills` | 判断任务阶段并协调完整工作流 | 下一阶段或完整结果 |
| `$poem-content` | 提炼长文、证据、边界和逐卡文案 | `ContentPlan` |
| `$poem-title` | 写封面承诺、准确换行和发布文案包 | `TitlePlan` |
| `$poem-design` | 选择版式、语义配图并生成卡片规格 | `DesignPlan`、`CardSpec[]` |
| `$poem-render` | 确定性排中文、渲染 PNG 和像素 QA | `ArtifactManifest` |
| `$poem-review` | 审查内容、视觉、手机阅读和发布状态 | `ReviewReport` |

完整流程：

```text
ContentPlan -> TitlePlan -> DesignPlan -> CardSpec[] -> ArtifactManifest -> ReviewReport
```

纯规划对话可以使用内联 `provisional` 产物；开始生产图片后，阶段产物必须落盘并使用 SHA-256 摘要绑定上游。旧文案、旧规格或旧 QA 不能静默进入新一轮生成。

## 安装

```bash
git clone https://github.com/Eliotcute/PoemSkills.git
cd PoemSkills
python3 scripts/install_skills.py
```

安装脚本默认同时安装到 Codex 和 Claude Code，只创建以下软链接，并拒绝覆盖无关目录：

```text
~/.codex/skills/{poemskills,poem-content,poem-title,poem-design,poem-render,poem-review}
~/.claude/skills/{poemskills,poem-content,poem-title,poem-design,poem-render,poem-review}
```

脚本会在写入前检查两端；若遇到意外写入失败，会保留已经正确创建的链接，直接重跑即可安全补齐。

只装一端：

```bash
python3 scripts/install_skills.py --host codex
python3 scripts/install_skills.py --check --host codex

python3 scripts/install_skills.py --host claude
python3 scripts/install_skills.py --check --host claude
```

重启 Codex 后使用 `$poemskills`。在 Claude Code 里用 `Skill` 工具按名字调用（`poemskills`、`poem-content` 等），文档中的 `$` 前缀是 Codex 调用语法。默认双端安装后可一起检查：

```bash
python3 scripts/install_skills.py --check
```

## 快速使用

不知道该调用哪个阶段：

```text
使用 $poemskills，把下面的长文做成一张封面和五张内页卡片，直接执行到可发布审查。

内容：
【粘贴长文】
```

只提炼文字，不出图：

```text
使用 $poem-content，把这段长文提炼成封面方向和五张内页文字稿，不做视觉设计。
```

只修改封面和发布标题：

```text
使用 $poem-title，根据已经确认的 ContentPlan 给出三个封面候选、准确换行和三个发布标题。
```

只要视觉方案和 Prompt：

```text
使用 $poem-design，把确认后的文案做成三种内容驱动的版式选择，并输出无文字配图 Prompt 和最终合成 Prompt，不生成图片。
```

需要整组逐卡 Prompt 时，每张卡会分别得到素材 Prompt 和合成 Prompt；纯文字卡只有合成 Prompt。不会用一条图片指令生成整组拼版。

直接渲染已有规格：

```text
使用 $poem-render，渲染 card-01.json 到 card-06.json。每张独立输出，不拼图。
```

检查并迭代成品：

```text
使用 $poem-review，检查这组卡片的内容准确性、配图相关性、手机阅读和系列节奏；先报告问题，再修正最低分项。
```

## 默认视觉系统

- 干净明亮的浅白纤维纸，纹理近看可见但不抢内容；
- 克制的宋体或明体中文层级；
- 一个低饱和强调色，覆盖面积通常不超过 5%；
- 默认一个主题素材，最多两个；
- 图片必须直接解释、证明、比较或准确象征本张论点；
- 每张卡片独立输出，禁止双联、宫格和比较板；
- 以 375 px 手机预览检查标题、正文和层级。

版式不再依赖一个万能模板。系统按卡片职责选择：图片在上文字在下、文字在上图片在下、左右穿插、纯文字编辑页、证据图加边缘注释、来源索引页。相邻卡片必须同时改变视觉机制或焦点区域。

## 支持规格

| 用途 | 尺寸 |
| --- | ---: |
| 小红书竖版 | 1242×1660 |
| 公众号主封面 | 900×383 |
| 公众号方形封面 | 500×500 |
| 公众号内文竖图 | 1080×1440 |
| 16:9 横版 | 1920×1080 |
| 9:16 竖版 | 1080×1920 |
| 1:1 方形 | 1080×1080 |
| 4:5 竖版 | 1080×1350 |
| 3:2 横版 | 1800×1200 |
| 自定义 | 明确宽高 |

不同尺寸会重新构图，不直接裁切同一母版。

确定性中文渲染目前要求 macOS，并至少安装一种系统字体：Songti SC、STHeiti 或 Arial Unicode。缺少可用中文字体时渲染会明确失败，不会静默退回可能产生方框字的默认字体。外部素材长边不得超过 8192 px，总像素不得超过 3200 万；自定义画布长边不得超过 4096 px，总像素不得超过 850 万。

## 渲染与审查

渲染一个或多个 CardSpec：

```bash
python3 scripts/run_pipeline.py card-01.json card-02.json
```

该命令会校验规格与系列节奏、渲染独立 PNG、生成手机预览、运行像素 QA，并创建待填写的视觉评分文件。生成完成不等于可发布。

检查图片并完成视觉评分后最终化：

```bash
python3 scripts/run_pipeline.py --finalize card-01.json card-02.json
```

最终化要求每个视觉类别至少 8/10、总分至少 85/100，且规格、PNG、预览、像素 QA 与视觉评分的摘要全部一致。

## 阶段合同

合同定义见 [`references/stage-contracts.md`](references/stage-contracts.md)。验证示例：

```bash
python3 scripts/validate_stage_artifact.py content-plan.json --source source.txt
python3 scripts/validate_stage_artifact.py title-plan.json --upstream content-plan.json
python3 scripts/validate_stage_artifact.py design-plan.json --upstream content-plan.json title-plan.json
python3 scripts/validate_stage_artifact.py artifact-manifest.json --upstream card-01.json card-02.json
```

现有 v0.6 CardSpec 通过显式 `python3 scripts/run_pipeline.py --legacy-v0.6 old-card.json` 保持兼容。缺少合同的规格不会再自动降级。新 CardSpec 使用：

```json
{
  "contract": "poem-card-spec/v1",
  "status": "validated",
  "content_plan_ref": "content-plan.json",
  "content_plan_digest": "sha256...",
  "title_plan_ref": "title-plan.json",
  "title_plan_digest": "sha256...",
  "design_plan_ref": "design-plan.json",
  "design_plan_digest": "sha256...",
  "design_variant_id": "selected-variant-id"
}
```

## 仓库结构

```text
PoemSkills/
├── SKILL.md                    # 薄路由与阶段协调器
├── skills/
│   ├── poem-content/
│   ├── poem-title/
│   ├── poem-design/
│   ├── poem-render/
│   └── poem-review/
├── agents/openai.yaml
├── assets/
├── references/
└── scripts/
```

详细视觉规则在 `references/style-system.md`，发布门禁在 `references/visual-quality-rubric.md`，确定性渲染器在 `scripts/render_card.py`。

## 测试

```bash
python3 scripts/test_skill_routes.py
python3 scripts/test_install_skills.py
python3 scripts/test_stage_contracts.py
python3 scripts/test_layout_contracts.py
python3 scripts/test_matrix.py
python3 scripts/test_intentional_intersection.py
python3 scripts/test_typography.py
python3 scripts/test_asset_gate.py
python3 scripts/test_visual_review.py
python3 scripts/test_content_contract.py
python3 scripts/test_series_contract.py
python3 scripts/test_finalize_integrity.py
```

校验六个 Skill 的结构：

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py" .
python3 "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py" skills/poem-content
```

## 核心约束

- 先明确内容，再写标题，再决定视觉；
- 封面是继续滑动的承诺，不是全文摘要；
- 一张内页只讲一个论点；
- 不为气氛添加无关素材、虚构日期、坐标、票据或档案；
- 中文由确定性排版完成，不交付错字或乱码；
- 未通过当前像素 QA 和视觉审查的图片不能标记为可发布。

## 本地 Git

```bash
git status
git log --oneline --decorate
```

最近公开版本标签为 `v0.6.1`。这套模块化结构将作为下一版本发布。
