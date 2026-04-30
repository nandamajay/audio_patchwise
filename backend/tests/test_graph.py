from app.agents.graph import patchwise_graph


def test_graph_runs_to_completion() -> None:
    state = {
        "session_id": "s1",
        "patch_input": "Subject: ASoC: clean patch\n\nSigned-off-by: Test <test@example.com>\n",
        "kernel_version": "6.9",
        "subsystem": "alsa-asoc",
        "source_path": "sound/soc/",
        "llm_model": "gpt-4o",
        "max_rounds": 2,
        "current_round": 1,
        "review_findings": [],
        "fix_attempts": [],
        "similar_patches": [],
        "current_patch": "Subject: ASoC: clean patch\n\nSigned-off-by: Test <test@example.com>\n",
        "verdict": "PENDING",
        "interrupt_hint": None,
        "conversation_log": [],
        "quality_score": 0.0,
        "messages": [],
    }

    out = patchwise_graph.invoke(state)
    assert out["verdict"] in {"LGTM", "NEEDS_WORK", "PENDING"}
    assert out["current_round"] <= 2
