#!/usr/bin/env python3
"""Regression tests for PoemSkills stage contracts."""

from __future__ import annotations

import copy
import json
import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path

from validate_stage_artifact import combined_digest, validate
from validate_visual_review import CATEGORIES


def write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    assert validate([]) == ["artifact must contain a JSON object"]
    with tempfile.TemporaryDirectory(prefix="poemskills-stage-contracts-") as raw:
        root = Path(raw)
        source_path = root / "source.txt"
        source_path.write_text("任务需要在真实代码仓库中完成", encoding="utf-8")
        content_path = root / "content-plan.json"
        content = {
            "contract": "poem-content-plan/v1",
            "status": "validated",
            "output_scope": "cover-plus-interiors",
            "source_ref": "user-source.md",
            "source_digest": combined_digest([source_path]),
            "topic": "测试主题",
            "reader_tension": "读者需要理解变化",
            "reader_payoff": "读者能够作出判断",
            "strongest_evidence": "来源中的具体机制",
            "boundaries": "不虚构来源没有证明的结果",
            "desired_action": "继续阅读",
            "cover_direction": "说明核心变化",
            "cards": [{
                "card_id": "02",
                "role": "mechanism",
                "claim": "任务必须进入真实环境",
                "source_excerpt": "任务需要在真实代码仓库中完成",
                "body": "模型需要调用真实工具并沿开发流程推进。",
                "reason_to_exist": "解释核心机制",
                "image_need": True,
                "image_role": "explain",
            }],
        }
        write(content_path, content)
        assert validate(content, source=source_path) == []

        empty_card_field = copy.deepcopy(content)
        empty_card_field["cards"][0]["claim"] = "   "
        assert any("cards[0].claim" in error for error in validate(empty_card_field, source=source_path))
        invalid_image_decision = copy.deepcopy(content)
        invalid_image_decision["cards"][0]["image_need"] = False
        assert any("image_role must be none" in error for error in validate(invalid_image_decision, source=source_path))

        cover_only = dict(content)
        cover_only["output_scope"] = "cover-only"
        cover_only["cards"] = []
        assert validate(cover_only, source=source_path) == []
        cover_only_with_card = copy.deepcopy(content)
        cover_only_with_card["output_scope"] = "cover-only"
        assert any("must not contain interior cards" in error for error in validate(cover_only_with_card, source=source_path))

        title = {
            "contract": "poem-title-plan/v1",
            "status": "validated",
            "content_plan_digest": combined_digest([content_path]),
            "cover_candidates": ["任务进入真实环境", "从演示走向真实工程", "代理必须调用真实工具"],
            "selected_cover": {
                "title": "任务进入真实环境",
                "lines": ["任务进入", "真实环境"],
                "subtitle": "从演示走向真实工程",
                "selection_reason": "准确表达原文变化",
            },
            "publishing_titles": ["AI编程进入真实工程"],
            "selected_publishing_title": "AI编程进入真实工程",
            "publication_package": {
                "xiaohongshu": {
                    "title": "AI编程进入真实工程",
                    "body": "当代理进入真实代码仓库，能力判断也要从演示转向工程验证。",
                    "tags": ["AI编程", "软件工程"],
                },
                "wechat": {
                    "title": "AI编程进入真实工程",
                    "summary": "从真实工具调用理解代理能力的变化。",
                },
                "alt_text": "浅白纤维纸上的中文编辑卡片，标题为任务进入真实环境。",
            },
        }
        assert validate(title, [content_path]) == []
        empty_candidate = copy.deepcopy(title)
        empty_candidate["cover_candidates"][1] = ""
        assert any("cover_candidates[1]" in error for error in validate(empty_candidate, [content_path]))
        incomplete_package = copy.deepcopy(title)
        incomplete_package["publication_package"]["xiaohongshu"]["body"] = ""
        assert any("publication_package.xiaohongshu.body" in error for error in validate(incomplete_package, [content_path]))
        assert any("requires at least 1 upstream" in error for error in validate(title))
        assert validate(title, [root / "missing-content-plan.json"])
        title["content_plan_digest"] = "0" * 64
        assert any("stale" in error for error in validate(title, [content_path]))

        title["content_plan_digest"] = combined_digest([content_path])
        title_path = root / "title-plan.json"
        write(title_path, title)
        design = {
            "contract": "poem-design-plan/v1",
            "status": "validated",
            "content_plan_digest": combined_digest([content_path]),
            "title_plan_digest": combined_digest([title_path]),
            "canvas": "xhs-portrait",
            "reference_contract": {"paper": "pale-white-fiber"},
            "variants": [{
                "variant_id": "image-above",
                "name": "图片在上文字在下",
                "layout_family": "vertical-editorial",
                "allowed_layouts": ["image-above"],
                "asset_strategy": "one topical relief print",
                "composition": "upper image and lower copy",
                "why": "fits mechanism explanation",
            }, {
                "variant_id": "text-led",
                "name": "纯文字编辑页",
                "layout_family": "text-led-note",
                "allowed_layouts": ["text-led-note"],
                "asset_strategy": "no asset",
                "composition": "one readable proposition and one support block",
                "why": "keeps the claim primary",
            }],
            "selected_variant": None,
            "production_ready": False,
            "card_specs": [],
        }
        assert validate(design, [content_path, title_path]) == []
        ready_design = dict(design)
        ready_design["production_ready"] = True
        ready_design["selected_variant"] = "image-above"
        ready_design["card_specs"] = ["card-01.json"]
        design_path = root / "design-plan.json"
        write(design_path, ready_design)
        array_spec_path = root / "array-card.json"
        array_spec_path.write_text("[]", encoding="utf-8")
        array_design = dict(ready_design)
        array_design["card_specs"] = ["array-card.json"]
        assert any(
            "must contain a JSON object" in error
            for error in validate(array_design, [content_path, title_path], artifact_path=design_path)
        )
        card_spec = {
            "contract": "poem-card-spec/v1",
            "status": "validated",
            "content_plan_ref": "content-plan.json",
            "content_plan_digest": combined_digest([content_path]),
            "title_plan_ref": "title-plan.json",
            "title_plan_digest": combined_digest([title_path]),
            "design_plan_ref": "design-plan.json",
            "design_plan_digest": combined_digest([design_path]),
            "design_variant_id": "image-above",
            "card_role": "cover",
            "source_ref": "user-source.md",
            "source_excerpt": "任务需要在真实代码仓库中完成",
            "card_claim": "任务进入真实环境",
            "canvas_preset": "xhs-portrait",
            "width": 1242,
            "height": 1660,
            "priority": "balanced",
            "render_mode": "final",
            "layout": "image-above",
            "cluster_zone": "middle-left",
            "title": "任务进入\n真实环境",
            "body": "从真实代码仓库开始验证代理能力",
            "assets": [{
                "type": "color-block",
                "motif": "sequence",
                "subject": "任务进入真实环境的顺序变化",
                "semantic_role": "sequence",
                "semantic_reason": "用顺序图形解释任务从演示进入真实工程环境",
            }],
            "output": "cover.png",
        }
        card_path = root / "card-01.json"
        write(card_path, card_spec)
        assert validate(ready_design, [content_path, title_path], artifact_path=design_path) == []
        pipeline_result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parent / "run_pipeline.py"), str(card_path)],
            text=True,
            capture_output=True,
        )
        assert pipeline_result.returncode == 0, pipeline_result.stderr
        rendered_qa = json.loads((root / "cover.png.qa.json").read_text(encoding="utf-8"))
        assert rendered_qa.get("valid") is True

        rogue_spec = dict(card_spec)
        rogue_spec["output"] = "rogue-cover.png"
        rogue_path = root / "rogue-card.json"
        write(rogue_path, rogue_spec)
        rogue_result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parent / "validate_card_spec.py"), str(rogue_path)],
            text=True,
            capture_output=True,
        )
        assert rogue_result.returncode != 0 and "not listed in design_plan_ref" in rogue_result.stdout
        card_spec["design_plan_digest"] = "0" * 64
        write(card_path, card_spec)
        assert any(
            "different DesignPlan" in error
            for error in validate(ready_design, [content_path, title_path], artifact_path=design_path)
        )
        card_spec["design_plan_digest"] = combined_digest([design_path])
        write(card_path, card_spec)

        image_path = root / "cover.png"
        preview_path = root / "cover-preview.png"
        qa_path = root / "cover.png.qa.json"
        layout_path = root / "cover.png.layout.json"
        visual_path = root / "cover.png.visual-review.json"
        image_path.write_bytes(b"image")
        preview_path.write_bytes(b"preview")
        digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
        write(layout_path, {"valid": True})
        write(qa_path, {
            "valid": True,
            "spec_sha256": digest(card_path),
            "image_sha256": digest(image_path),
            "preview_sha256": digest(preview_path),
            "layout_sha256": digest(layout_path),
        })
        write(visual_path, {
            "status": "approved",
            "image": str(image_path),
            "preview": str(preview_path),
            "image_sha256": digest(image_path),
            "preview_sha256": digest(preview_path),
            "scores": {category: 8.5 for category in CATEGORIES},
            "lowest_category": "composition",
            "revision_summary": "检查完整图片与手机预览，并确认全部发布门禁。",
            "approved": True,
        })
        manifest = {
            "contract": "poem-artifact-manifest/v1",
            "status": "validated",
            "card_specs_digest": combined_digest([card_path]),
            "valid": True,
            "finalized": True,
            "pixel_valid": True,
            "deliverable": True,
            "outputs": [{
                "spec": str(card_path),
                "image": str(image_path),
                "preview": str(preview_path),
                "qa": str(qa_path),
                "qa_sha256": digest(qa_path),
                "layout": str(layout_path),
                "layout_sha256": digest(layout_path),
                "visual_review": str(visual_path),
                "visual_review_sha256": digest(visual_path),
            }],
        }
        manifest_path = root / "artifact-manifest.json"
        write(manifest_path, manifest)
        assert validate(manifest, [card_path], artifact_path=manifest_path) == []
        alternate_card_path = root / "alternate-card.json"
        alternate_card = dict(card_spec)
        alternate_card["output"] = "alternate-cover.png"
        write(alternate_card_path, alternate_card)
        assert any(
            "exactly the bound CardSpec" in error
            for error in validate(manifest, [alternate_card_path], artifact_path=manifest_path)
        )

        forged_manifest = dict(manifest)
        forged_manifest["card_specs_digest"] = combined_digest([alternate_card_path])
        forged_manifest_path = root / "forged-artifact-manifest.json"
        write(forged_manifest_path, forged_manifest)

        review_report = {
            "contract": "poem-review-report/v1",
            "status": "validated",
            "artifact_manifest_digest": combined_digest([manifest_path]),
            "approved": True,
            "deliverable": True,
            "scores": {category: 8.5 for category in CATEGORIES},
            "lowest_category": "composition",
            "revision_summary": "全部像素与视觉证据已完成验证。",
            "remaining_risk": "无已知阻断风险",
        }
        assert validate(review_report, [manifest_path]) == []
        fake_scores = copy.deepcopy(review_report)
        fake_scores["scores"] = {"fake": 0}
        assert any("exactly the visual review categories" in error for error in validate(fake_scores, [manifest_path]))
        wrong_lowest = copy.deepcopy(review_report)
        wrong_lowest["scores"]["material_quality"] = 8.0
        assert any("lowest_category" in error for error in validate(wrong_lowest, [manifest_path]))
        empty_revision = copy.deepcopy(review_report)
        empty_revision["revision_summary"] = ""
        assert any("revision_summary" in error for error in validate(empty_revision, [manifest_path]))
        empty_risk = copy.deepcopy(review_report)
        empty_risk["remaining_risk"] = ""
        assert any("remaining_risk" in error for error in validate(empty_risk, [manifest_path]))
        evidence_mismatch = copy.deepcopy(review_report)
        evidence_mismatch["scores"]["semantic_specificity"] = 9.0
        assert any("must equal the lowest score" in error for error in validate(evidence_mismatch, [manifest_path]))
        assert any("requires at least 1 upstream" in error for error in validate(review_report))
        forged_report = dict(review_report)
        forged_report["artifact_manifest_digest"] = combined_digest([forged_manifest_path])
        assert any(
            "does not match ArtifactManifest outputs" in error
            for error in validate(forged_report, [forged_manifest_path])
        )

        write(layout_path, {"valid": True, "mutated": True})
        assert any(
            "changed after ArtifactManifest" in error
            for error in validate(review_report, [manifest_path])
        )
        write(layout_path, {"valid": True})

        missing_manifest = dict(manifest)
        missing_manifest["outputs"] = [dict(manifest["outputs"][0], image=str(root / "missing.png"))]
        missing_manifest_path = root / "missing-artifact-manifest.json"
        write(missing_manifest_path, missing_manifest)
        unsafe_report = dict(review_report)
        unsafe_report["artifact_manifest_digest"] = combined_digest([missing_manifest_path])
        assert any(
            "does not exist" in error
            for error in validate(unsafe_report, [missing_manifest_path])
        )

        missing_selection = dict(design)
        missing_selection["production_ready"] = True
        missing_selection["selected_variant"] = "missing"
        missing_selection["card_specs"] = ["missing.json"]
        assert validate(missing_selection, [content_path, title_path])

        content["source_digest"] = "0" * 64
        assert any("different source" in error for error in validate(content, source=source_path))
        content["source_digest"] = combined_digest([source_path])
        assert any("requires --source" in error for error in validate(content))

        provisional = dict(content)
        provisional["status"] = "provisional"
        assert any("status: validated" in error for error in validate(provisional, source=source_path))

        broken = dict(content)
        broken.pop("cards")
        assert validate(broken)
    print("stage contracts: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
