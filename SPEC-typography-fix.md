# SPEC: 排版与字体修复 + 双端安装

日期：2026-07-26
范围：`scripts/render_card.py`、`scripts/qa_card.py`、`scripts/validate_card_spec.py`、`scripts/install_skills.py`、相关 `scripts/test_*.py`、`README.md`、根 `SKILL.md`、`skills/*/SKILL.md`
不在范围：接真实生图能力（下一阶段）、一句话快通道、流程门禁简化

## 问题（已实测，非推测）

实渲 `assets/e2e/card-02.json` 得到的图：大片空白 + 左下一坨粗黑宋体 + 右下一个蓝方块。

### P0-1 字重层级不存在

`render_card.py:30-33` 的 `SERIF_FONTS` 首选 `Songti.ttc`，`load_font()` 第 50 行硬编码 `index=0`。

`Songti.ttc` 实际含 8 个 face：

| index | 字族 | 字重 |
| ---: | --- | --- |
| 0 | Songti SC | **Black** ← 当前实际使用 |
| 1 | Songti SC | Bold |
| 3 | Songti SC | Light |
| 4 | STSong | Regular |
| 6 | Songti SC | Regular |

`render_card.py:336-337` 中 `title_font` 与 `body_font` 都调 `load_font(size, "serif")`，因此**标题和正文拿到同一个 Songti SC Black**，填充色都是 `INK`。层级只靠字号（82 vs 40）区分 —— 违反 `style-system.md:31-34` 要求的"克制的宋体或明体"与"层级restrained"。

### P0-2 正文与标题同色同重，视觉上糊成一块

`render_card.py:372,377` 两个 `draw_text_block` 都传 `INK`。`style-system.md:18-19` 定义了 `Secondary ink: #565650`（代码里是 `MUTED`），但正文完全没用上。

### P1-3 自带示例过不了自身门禁

`assets/e2e/card-*.json` 缺 `contract` / `status` / `*_digest`，直接渲报错：
`legacy v0.6 CardSpec requires explicit --legacy-v0.6`。
原有 11 个测试全 PASS 但无一个测试检查视觉产出，因此能"全绿"地交付上面那张图。

### P1-4 只能装在 Codex

`install_skills.py` 只软链 `~/.codex/skills/`。用户需要 Claude Code 也能调用。

## 修改方案

### 1. 字体层级（`render_card.py`）

`load_font()` 增加 `weight` 参数，从 `(path, index)` 元组表中选 face：

```
SERIF_FACES = {
  "title":   Songti.ttc index 1 (Songti SC Bold)
  "body":    Songti.ttc index 6 (Songti SC Regular)
  "support": Songti.ttc index 3 (Songti SC Light)
}
```

保留系统字体 fallback 链：标题降级到 `STHeiti Medium.ttc` index 1（`Heiti SC Medium`），正文和辅助字降级到 `STHeiti Light.ttc` index 1（`Heiti SC Light`），再降级到 `Arial Unicode`；仍无可用中文字体时显式失败。回退测试必须让 Pillow 加载真实 face 并检查 `getname()`，不能只 mock 路径与 index 元组。
**约束**：不新增第三方字体依赖，只用系统已有 face。

验证：`title_font.getname()` 返回 Bold，`body_font.getname()` 返回 Regular。

### 2. 正文改用 secondary ink

`render_card.py:377` 正文填充由 `INK` 改为 `MUTED`。
**约束**：`style-system.md:128` 要求正文对纸张对比度 ≥ 4.5:1。`MUTED (86,86,80)` vs `PAPER (250,250,247)` 需实测对比度，不达标则改用介于两者之间的第三档墨色而非直接放弃。

### 3. 行距与字号

`title_gap = title_px * 0.42` 对中文标题偏紧，调整为 `0.52`，使当前宋体在各档整数字号下的多行标题达到至少 1.4 倍行距。正文改为 `0.62`，并按 `style-system.md:124-126` 的 px 区间复核字号表。

### 3.5 纸张纹理

提高短纤维密度并加入少量长纤维，使白纸在近看时具有纸莎草触感；保持 `style-system.md:27` 规定的白色基底、大片净白和约 4% 以内纹理对比，不增加黄褐、污渍或旧纸效果。

### 4. 双端安装（`install_skills.py`）

增加 `--host codex|claude|both`，默认 `both`。软链目标扩展到 `~/.claude/skills/`。
保留现有"拒绝覆盖无关目录"的安全检查。

根 `SKILL.md` 说明 `$poem-content` 是 Codex 调用语法，Claude Code 按裸 skill name 调用。五个 specialist 不再依赖软链接下不稳定的 `../../` 或当前工作目录，统一先解析绝对 `POEMSKILLS_ROOT`，再读取参考文件或运行脚本。

### 5. 示例卡片补齐合同（P1，可选）

给 `assets/e2e/card-*.json` 补 `contract`/`status`/`*_digest`，使 `python3 scripts/run_pipeline.py assets/e2e/card-01.json` 不加 legacy 开关即可跑通。
**风险**：这些是测试资产，改动会影响 `test_stage_contracts.py` 等。需先确认哪些测试依赖其"legacy"属性，不可为了跑通而弱化校验逻辑。

## 验证步骤

1. 改 `load_font` → 验证：Songti 的 `title_font.getname()[1] == 'Bold'`、`body_font.getname()[1] == 'Regular'`；模拟 Songti 不可用时，真实 STHeiti face 必须分别为 `Heiti SC Medium/Light/Light`
2. 改正文色 → 验证：自动测试和 QA 报告均要求 `MUTED` vs `PAPER` 对比度 ≥ 4.5:1，且 `essential_contrast` 取标题/正文的较低值
3. 重渲 card-02 → 验证：肉眼对比修改前后两张 PNG，标题与正文有可见字重差
4. 跑全部 12 个测试 → 验证：全部仍 PASS（不得为通过而修改测试断言）
5. 改安装脚本 → 在隔离的 `CODEX_HOME` 与 `CLAUDE_CONFIG_DIR` 下验证默认安装和 `--check` 同时覆盖两端，`--host codex` 只安装一端
6. 375px 预览 → 验证：10 种画布 × 7 种布局的 70 个内页样本，加每种画布 1 个封面样本，共 80 个显式多行样本全部通过；`style-system.md:127` 要求核心句在手机预览下无需缩放即可读，并验证标题/正文行距
7. 素材完整性 → 保留全部 sidecar、只擦除任意 500 个已验证素材贡献像素时，QA 必须拒绝；素材尺寸、位置与透明度必须匹配由 CardSpec 重建的 canonical asset plan；后续素材只有 alpha ≥ 32 的像素可排除较早素材贡献，透明矩形区域不可用于隐藏擦除
8. 发布权限 → 新生成的 PNG、preview、alpha、layout、QA、visual-review 与 manifest 必须为 `0644`

## 显式不做

- 不接生图 API（用户指定本阶段只修排版字体）
- 不删任何现有校验或门禁逻辑
- 不改 references/*.md 的视觉规范本身，只在与代码不一致处记录差异
- 不为让测试通过而放宽断言

## 审计补充（2026-07-28）

- 自定义画布限制为长边 4096 px、总像素 850 万，避免渲染阶段内存耗尽。
- 外部素材限制为长边 8192 px、总像素 3200 万，并在校验和实际解码两处检查。
- 输出必须解析在 CardSpec 所在目录内；拒绝绝对路径、`..` 和软链接逃逸。
- 布局元数据必须声明准确的纸张、标题和正文 RGB；QA 同时检查实际文字框内的像素颜色。
- renderer 与 QA 从 CardSpec、画布、布局、区域和确定性文字布局共享重建 canonical asset plan；素材 box、位置与 opacity 必须精确匹配，拒绝 PNG/layout/alpha 三者自洽但缩小或移位的伪造结果。
- QA 会从 CardSpec 素材、canonical 尺寸、透明度与 seed 重新生成 alpha 证据，拒绝伪造或过期的透明度 sidecar。
- QA 还会重建每个素材对画布的可见像素贡献并与最终 PNG 对照；未被确定性文字或后续素材不透明像素覆盖排除的贡献像素要求 100% 匹配。后续素材仅按重建 alpha ≥ 32 的像素排除，不按整个矩形排除。
- PNG、alpha、layout、preview、QA、visual-review 与 manifest 使用同目录临时文件原子替换并显式设为 `0644`，避免派生路径软链接覆盖目录外文件，同时保持跨账户发布服务可读。
- CardSpec、上游阶段产物和布局元数据设置 1 MB JSON 读取上限，超限时结构化拒绝。
- 缺失、畸形或超限的系列与视觉审查 JSON 必须输出结构化 `INVALID`，退出码为 1，且不得泄露 Python traceback。
- 封面副标题保持可选；`body: ""` 时 renderer 可输出空 `body_boxes`，QA 不要求正文像素证据，但内页与声明了正文的封面仍执行完整正文门禁。
- 10 种画布 × 7 种布局的 70 个内页样本，加每种画布 1 个封面样本，共 80 个样本均按 375 px 宽度检查标题与正文；小红书预览固定为 375×500，其他比例等比缩放，显式多行标题和正文均有行距回归证据。
- 纸张纤维要求同一 seed 可复现、可见像素占比受控，且任一通道偏差不超过 10/255。
- 缺少受支持的中文字体时显式失败，不再使用 Pillow 默认字体静默降级；STHeiti 回退必须使用 index 1 的简体中文 face，避免标题与正文混用繁简字形。
- 双端安装先完整预检再写入；意外写失败时保留已成功创建的正确链接，避免并发回滚误删，并支持直接重跑补齐。
- 五个 specialist 提供 Codex/Claude Code 各自可执行的 `POEMSKILLS_ROOT` 解析命令，并通过临时双端软链、非仓库工作目录和真实脚本调用验证；单端安装文档使用匹配的 `--host ... --check`。
