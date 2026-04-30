from app.skills.patchwise_skill import (
    check_lkml_compliance,
    check_memory_safety,
    check_kernel_style,
    search_similar_patches,
    full_patch_analysis,
)


def test_checkpatch_analyzer_with_sample_patch() -> None:
    sample = "Subject: fix\n+\tint x = 0;\n"
    issues = check_kernel_style(sample)
    assert any(item["issue_type"] == "STYLE" for item in issues)


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
