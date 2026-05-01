import app.skills.patchwise_skill as patchwise_skill
from app.skills.patchwise_skill import (
    check_lkml_compliance,
    check_memory_safety,
    check_kernel_style,
    search_similar_patches,
    full_patch_analysis,
)


def test_checkpatch_analyzer_with_sample_patch(monkeypatch) -> None:
    sample = "Subject: fix\n+\tint x = 0;\n"

    monkeypatch.setattr(
        patchwise_skill,
        "run_checkpatch",
        lambda _patch: {
            "status": "issues",
            "output": "WARNING:LINE_SPACING: please, no spaces at the start of a line\n#2: FILE: foo.c:2:",
        },
    )
    issues = check_kernel_style(sample)
    assert any(item["issue_type"] == "STYLE" for item in issues)
    assert any("checkpatch:" in item["description"] for item in issues)


def test_checkpatch_missing_does_not_flood_style_issues(monkeypatch) -> None:
    monkeypatch.setattr(
        patchwise_skill,
        "run_checkpatch",
        lambda _patch: {"status": "skipped", "reason": "missing", "output": ""},
    )
    issues = check_kernel_style("Subject: fix\n+\tint x = 0;\n")
    assert issues == []


def test_checkpatch_check_findings_are_filtered_by_default(monkeypatch) -> None:
    monkeypatch.setattr(
        patchwise_skill,
        "run_checkpatch",
        lambda _patch: {
            "status": "issues",
            "output": "CHECK:LONG_LINE: line length of 90 exceeds 80 columns\n#3: FILE: foo.c:3:",
        },
    )
    issues = check_kernel_style("Subject: fix\n+int x = 0;\n")
    assert issues == []


def test_lsp_context_extractor_finds_symbols() -> None:
    sample = "+int snd_soc_register_component(void);\n"
    findings = full_patch_analysis(sample, "sound/soc/")
    assert "logic" in findings


def test_upstream_compliance_checker_flags_missing_signoff() -> None:
    sample = "Subject: ASoC: sample\n\nbody only"
    issues = check_lkml_compliance(sample)
    assert any("Signed-off-by" in item["description"] for item in issues)


def test_semantic_search_returns_related_patches() -> None:
    refs = search_similar_patches("ASoC fix", "alsa-asoc", sources=["lkml", "local"])
    assert len(refs) >= 1
    assert any(ref.get("url") for ref in refs)


def test_review_report_builder_structure() -> None:
    sample = "Subject: fix audio\n+void *p = kmalloc(16, GFP_KERNEL);\n"
    report = full_patch_analysis(sample, "sound/soc/")
    assert set(report.keys()) == {"style", "logic", "memory", "lkml", "commit"}
    assert isinstance(check_memory_safety(sample), list)
