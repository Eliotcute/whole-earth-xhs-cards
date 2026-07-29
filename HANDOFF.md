# PoemSkills Handoff

更新时间：2026-07-29  
下一阶段目标：修复发布合同 P1，完成 v1 发布样例并重新评分。

## Read first

1. [`PRD-PoemSkills.md`](PRD-PoemSkills.md) - 产品范围、P0/P1 要求和发布门禁。
2. [`SPEC-typography-fix.md`](SPEC-typography-fix.md) - 已完成实现与安全审计细节。
3. [`references/stage-contracts.md`](references/stage-contracts.md) - 阶段合同权威定义。
4. [`references/visual-quality-rubric.md`](references/visual-quality-rubric.md) - 视觉评分权威定义。
5. [`README.md`](README.md) - 用户命令和 12 个测试入口。

## Current state

- 排版、字体、纸张、素材完整性、双端安装和结构化错误处理已经实现。
- README 12 个测试脚本全部通过。
- 10 种画布 x 7 种布局的 70 个内页，加 10 个封面，共 80/80 通过。
- 20 个 Python 文件语法检查通过。
- 6 个 Skill frontmatter 的 Ruby/YAML 校验通过。
- staged、unstaged 和合并 diff checks 通过。
- 工程交付评分：87/100。
- 当前 card-02 独立视觉复核：79/100；保存的 review 文件记录 86/100。
- 当前发布结论：不通过。

## Blocking issue

`scripts/run_pipeline.py` 在 `--legacy-v0.6 --finalize` 下会写出：

```json
{
  "contract": "poem-artifact-manifest/v1",
  "status": "validated",
  "deliverable": true
}
```

但 `assets/e2e/card-02.json` 是 legacy CardSpec，没有 `poem-card-spec/v1` 和 `status: validated`。正式验证会失败：

```bash
python3 scripts/validate_stage_artifact.py \
  assets/e2e/artifact-manifest.json \
  --upstream assets/e2e/card-02.json
```

当前结果：

```text
INVALID
- CardSpec upstream 0 must use contract poem-card-spec/v1
- CardSpec upstream 0 must have status: validated
```

相关位置：

- `scripts/run_pipeline.py:153-163`
- `scripts/validate_stage_artifact.py:564-566`
- `scripts/test_finalize_integrity.py:22-27,124-138`
- `assets/e2e/card-02.json`
- `assets/e2e/artifact-manifest.json`

## Recommended next steps

1. 先确认 legacy 策略。推荐允许 render/QA，但禁止 legacy 直接 finalize；另一方案是提供显式完整 v1 迁移。
2. 修复 `run_pipeline.py`，保证任何 `deliverable: true` manifest 都能用真实上游通过正式阶段验证。
3. 在 `test_finalize_integrity.py` 增加回归：验证生成的 manifest，而不只检查字段和退出码。
4. 把发布样例迁移为完整 v1 上游链，或将现有 card-02 明确归类为 legacy fixture。
5. 生成至少一张封面和两张相邻内页，重新检查 series rhythm。
6. 优先改善 card-02 的 material quality 和 image-text relationship，再运行最终评分。
7. 重跑 README 全部测试、80 项矩阵、语法/frontmatter/diff checks 和安全复核。

## Worktree guardrails

- 当前工作树已有大量 staged 与 unstaged 改动，属于用户和前序任务。
- 不要 reset、checkout、清理、统一格式化或改变现有暂存状态。
- 未经用户要求，不要 commit、push 或安装依赖。
- `assets/e2e/artifact-manifest.json` 是本地生成物，已被 `.gitignore` 忽略，包含本机绝对路径，不应提交。
- 官方 `quick_validate.py` 因缺少 PyYAML 无法运行。不要自行安装；现有 Ruby/YAML 替代校验已通过。
- `scripts/render_card.py` 845 行，`scripts/qa_card.py` 667 行，均超过 500 行。P0 修复不要顺手重构。

## Verification commands

完整测试命令见 [`README.md`](README.md) 的“测试”章节。P0 修复至少额外运行：

```bash
python3 scripts/test_finalize_integrity.py
python3 scripts/test_stage_contracts.py
python3 scripts/validate_stage_artifact.py artifact-manifest.json --upstream card-01.json
git diff --check
git diff --cached --check
```

最后一条 manifest 命令中的路径应替换为测试产生的真实 v1 文件，不要用摘要占位符。

## Suggested skills

- `diagnosing-bugs` - 复现并定位 legacy finalize 与正式合同之间的矛盾。
- `implement` - 做最小 P0 修复并补回归。
- `poem-render` - 重新生成完整 v1 发布样例。
- `poem-review` - 检查真实图片、手机预览和十项视觉门禁。
- `review` - 在发布前做功能、质量、测试和安全复核。
