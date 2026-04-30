from app.agents.chanakya import chanakya_review_node


def test_chanakya_sets_needs_work_for_issues() -> None:
    state = {
        "session_id": "s1",
        "patch_input": "Subject: fix\n+\tint x = kmalloc(16, GFP_KERNEL);\n",
        "kernel_version": "6.9",
        "subsystem": "alsa-asoc",
        "source_path": "sound/soc/",
        "llm_model": "gpt-4o",
        "max_rounds": 5,
        "current_round": 1,
        "review_findings": [],
        "fix_attempts": [],
        "similar_patches": [],
        "current_patch": "Subject: fix\n+\tint x = kmalloc(16, GFP_KERNEL);\n",
        "verdict": "PENDING",
        "interrupt_hint": None,
        "conversation_log": [],
        "quality_score": 0.0,
        "messages": [],
    }

    out = chanakya_review_node(state)
    assert out["verdict"] == "NEEDS_WORK"
    assert len(out["review_findings"]) == 1
