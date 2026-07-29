# PRD: PoemSkills 可发布中文图文卡片生产线

状态：Draft，存在 1 个发布阻塞项  
更新日期：2026-07-29  
产品范围：PoemSkills 下一版本发布

## 1. Summary

PoemSkills 把中文长文转成可发布的小红书和公众号卡片。它把内容、标题、设计、渲染和审查拆成五个 Skill，并用阶段合同、确定性排版、像素 QA 和视觉评分控制质量。

下一版本的重点不是增加更多效果，而是让“可发布”成为可信结论。任何被标记为 `deliverable: true` 的产物，都必须通过正式阶段合同、当前像素 QA 和视觉门禁。

## 2. Contacts

| Name | Role | Comment |
| --- | --- | --- |
| 适之 Shizhi | Maintainer / Product Owner | 确认产品范围、兼容策略和发布决定 |
| 待指定 | Engineering Owner | 修复发布合同阻塞项并维护回归测试 |
| `$poem-review` 审查流程 | Release Reviewer | 检查真实图片、手机预览和十项视觉评分 |

## 3. Background

PoemSkills 已完成模块化改造，当前流程为：

```text
ContentPlan -> TitlePlan -> DesignPlan -> CardSpec[] -> ArtifactManifest -> ReviewReport
```

现有实现已经具备以下能力：

- Codex 与 Claude Code 双端软链安装；
- 10 种画布、7 种布局和 375 px 手机预览；
- 中文字体字重、正文颜色、行距和纸张纹理控制；
- CardSpec、图片、素材、布局和审查证据的完整性检查；
- 有界 JSON、画布、图片和输出路径校验；
- 原子写入与统一 `0644` 发布权限；
- 视觉评分最低单项 8/10、总分 85/100 的发布门禁。

现有实现细节和历史决策见 [`SPEC-typography-fix.md`](SPEC-typography-fix.md)。阶段合同以 [`references/stage-contracts.md`](references/stage-contracts.md) 为准，视觉标准以 [`references/visual-quality-rubric.md`](references/visual-quality-rubric.md) 为准。

### Current evidence

- README 中 12 个测试脚本全部通过；
- 80/80 画布与布局矩阵通过；
- 20 个 Python 文件语法检查通过；
- 6 个 Skill frontmatter 的 Ruby/YAML 校验通过；
- staged、unstaged 和合并 diff 检查通过；
- 当前工程交付评分为 87/100；
- 当前 `card-02` 独立视觉复核为 79/100，低于发布线。

### Why now

当前存在一个发布合同矛盾：`--legacy-v0.6 --finalize` 可以生成 `status: validated`、`deliverable: true` 的 v1 ArtifactManifest，但正式阶段校验会拒绝它，因为上游 CardSpec 不是 `poem-card-spec/v1`。系统不能一边宣称可交付，一边无法验证自己的交付合同。

## 4. Objective

### Objective

让 PoemSkills 的发布状态可验证、可复现、不可伪造，同时保留现有排版质量、双端安装和 legacy 显式兼容能力。

### Key Results

1. 所有标记为 `deliverable: true` 的 ArtifactManifest，使用其真实 CardSpec 上游运行 `validate_stage_artifact.py` 时必须 100% 通过。
2. legacy CardSpec 不得直接产生 `status: validated` 或 `deliverable: true` 的 v1 发布产物。
3. README 的 12 个测试脚本与 80 项渲染矩阵保持 100% 通过。
4. 每个发布卡片的像素 QA 必须有效，十项视觉评分每项至少 8/10，总分至少 85/100。
5. Codex 与 Claude Code 的安装、单端检查和从非仓库目录解析 `POEMSKILLS_ROOT` 的集成测试保持 100% 通过。
6. 缺失、畸形或超限输入必须结构化失败，不输出 traceback，不在目标目录外写文件。

## 5. Market Segments

### Chinese content creators

他们需要把长文变成清楚、克制、可在手机上阅读的卡片。他们不想手工处理每张图的字号、换行和导出尺寸。

### Editorial and social teams

他们需要一套可重复的流程。每张卡必须能追溯到原文，不能靠好看的无关素材替代内容。

### Codex and Claude Code users

他们希望用自然语言调用完整工作流，也希望单独调用内容、标题、设计、渲染或审查阶段。

### Maintainers and integrators

他们需要稳定的 JSON 合同、明确错误、可验证摘要和安全的本地文件行为。

### Constraints

- 确定性中文渲染当前以 macOS 系统字体为基础；
- 不假设存在真实生图 API；
- 外部图片必须由用户提供、合法授权或明确生成；
- 生产阶段必须使用文件-backed、`status: validated` 的上游产物；
- legacy 输入只能通过显式兼容入口处理。

## 6. Value Propositions

| Customer job | PoemSkills value | Pain avoided |
| --- | --- | --- |
| 把长文提炼成卡组 | 一张卡只承载一个明确论点 | 摘抄堆砌和信息过载 |
| 在手机上稳定排中文 | 字体、换行、行距和对比度确定性渲染 | 方框字、断行、过小正文 |
| 判断图片能否发布 | 像素 QA 与人工视觉评分分开执行 | “能导出”被误认为“能发布” |
| 跨 agent 继续生产 | 版本化合同和 SHA-256 上游绑定 | 旧文案、旧 QA 或旧图片混入新版本 |
| 在两个 host 使用 | Codex 与 Claude Code 双端安装 | 手动复制 Skill 和 cwd 路径错误 |
| 安全处理本地素材 | 大小限制、路径边界和原子写入 | 内存耗尽、路径逃逸和软链覆盖 |

## 7. Solution

### 7.1 UX and user flow

完整生产请求默认执行：

```text
输入原文
  -> 确认 ContentPlan
  -> 选择标题与 DesignPlan
  -> 生成独立 CardSpec
  -> 渲染 PNG 与手机预览
  -> 像素 QA
  -> 十项视觉评分
  -> 正式合同验证
  -> 发布或返回最低分阶段修改
```

用户请求“直接做到可发布”时，系统最多进行三轮修改。第三轮仍失败时，必须返回阻塞原因，并保持 `approved: false`、`deliverable: false`。

### 7.2 Key features and requirements

#### P0: Publication contract integrity

- `deliverable: true` 必须表示整个 v1 上游链可以被正式校验。
- `run_pipeline.py` 写出 manifest 后，最终化路径必须使用真实上游立即验证该 manifest。
- legacy 输入不得被包装成假的 validated v1 产物。
- 推荐行为：legacy 可以校验、渲染和运行像素 QA，但 `--legacy-v0.6 --finalize` 应返回非零退出码和迁移说明。
- 可选行为：提供显式迁移命令。只有补齐真实 ContentPlan、TitlePlan、DesignPlan 引用与摘要后，迁移结果才可进入 v1 最终化。
- `scripts/test_finalize_integrity.py` 必须覆盖 manifest 的正式阶段验证，而不只检查字段存在和退出码。
- 发布示例必须使用完整 v1 CardSpec；legacy 示例应明确放在兼容测试范围，不得作为已发布样例。

#### P0: Existing quality and safety gates

- 保持当前字体、颜色、行距、纸张纹理和手机预览阈值。
- 保持 canonical asset plan、alpha 证据和最终像素贡献检查。
- 保持 JSON、画布、图片和输出路径上限。
- 保持原子写入、`0644` 权限和目录边界。
- 合法无副标题封面可以通过；内页与有正文封面仍要求正文证据。

#### P1: Publishable sample set

- 将 `assets/e2e/card-02` 迁移为完整 v1 样例，或把它明确降级为 legacy fixture。
- 至少生成一张封面和两张相邻内页，才能检查真实系列节奏。
- 改善当前 card-02 的材料质量和图文关系。程序化蓝色方块不能承担主要视觉价值。
- 重新评分后每项至少 8/10，总分至少 85/100。

#### P1: Documentation

- README 必须清楚区分 render、pixel-valid、approved 和 deliverable。
- legacy 文档必须说明它是否可以最终化，以及如何迁移。
- 所有命令示例应能从文档声明的工作目录执行。

### 7.3 Technology

- Python 3 和 Pillow 负责确定性渲染与图片检查；
- JSON 文件承担阶段合同和证据绑定；
- SHA-256 绑定上游文件与 QA、layout、review sidecar；
- 本地软链接安装到 Codex 与 Claude Code；
- 不新增依赖，除非维护者先批准。

### 7.4 Assumptions and open decisions

- 假设发布环境存在 Songti SC、STHeiti 或 Arial Unicode 中至少一种字体。
- 假设用户负责外部素材版权与来源真实性。
- 官方 `quick_validate.py` 当前依赖 PyYAML；在依赖未批准前，以现有 Ruby/YAML 校验作为替代证据。
- 待 Product Owner 确认：legacy 最终化应直接禁止，还是通过显式迁移后继续。无论选择哪种方案，都不能再生成无法验证的 `deliverable: true`。

### Out of scope

- 接入真实生图 API；
- 自动发布到小红书或微信公众号；
- 云端账户、支付或协作后台；
- 为解决 P0 而重构整个 renderer 或 QA；
- 在本版本支持非 macOS 的完整字体一致性。

## 8. Release

### Gate 0: Contract fix

预计为一个小型工程迭代。完成 legacy 策略、manifest 自校验和回归测试。Gate 0 未通过时不得发布。

### Gate 1: Sample migration and visual review

预计为一个短迭代。迁移或重建发布样例，完成相邻卡片，并修正最低视觉类别。

### Gate 2: Release candidate

运行 README 全部测试、80 项矩阵、语法检查、Skill frontmatter 校验、diff checks 和安全复核。对候选样例运行完整阶段合同与视觉门禁。

### First release includes

- 五阶段 Skill 工作流；
- v1 文件合同和摘要绑定；
- 确定性中文渲染、像素 QA 和视觉评分；
- Codex 与 Claude Code 双端安装；
- 明确且不误报发布状态的 legacy 兼容策略。

### Future releases

- 真实生图或素材服务；
- 更多已验证的主题材料处理；
- 跨平台字体包与一致性测试；
- 可选的发布平台集成。

### Launch checklist

- [ ] P0 发布合同阻塞项已修复；
- [ ] legacy 策略已由 Product Owner 确认并写入 README；
- [ ] 成功最终化的 manifest 能通过正式阶段校验；
- [ ] README 12/12 测试和矩阵 80/80 通过；
- [ ] 发布样例像素 QA 有效；
- [ ] 十项视觉评分每项至少 8/10，总分至少 85/100；
- [ ] ReviewReport 与当前 ArtifactManifest 摘要一致；
- [ ] 无 secret、绝对本机路径或未跟踪生成物进入发布改动；
- [ ] `git diff --check` 和安全复核通过。
