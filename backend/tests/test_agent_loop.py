from app.agents.aryabhata import aryabhata_fix_node
from app.agents.chanakya import chanakya_review_node
from app.agents.graph import patchwise_graph


def _state(max_rounds: int = 3) -> dict:
    return {
        "session_id": "s-loop",
        "patch_input": "Subject: fix audio\n+\tvoid *ptr = kmalloc(16, GFP_KERNEL);\n",
        "kernel_version": "6.9",
        "subsystem": "alsa-asoc",
        "source_path": "sound/soc/",
        "llm_model": "gpt-4o",
        "max_rounds": max_rounds,
        "current_round": 1,
        "review_findings": [],
        "fix_attempts": [],
        "similar_patches": [],
        "current_patch": "Subject: fix audio\n+\tvoid *ptr = kmalloc(16, GFP_KERNEL);\n",
        "verdict": "PENDING",
        "interrupt_hint": None,
        "conversation_log": [],
        "quality_score": 0.0,
        "messages": [],
    }


def test_chanakya_node_produces_review_report() -> None:
    out = chanakya_review_node(_state())
    assert len(out["review_findings"]) == 1


def test_aryabhata_node_produces_fixed_patch() -> None:
    reviewed = chanakya_review_node(_state())
    fixed = aryabhata_fix_node(reviewed)
    assert fixed["current_round"] == 2
    assert len(fixed["fix_attempts"]) == 1


def test_full_loop_terminates_on_lgtm() -> None:
    clean = _state(max_rounds=3)
    clean["patch_input"] = "Subject: ASoC: clean patch\n\nSigned-off-by: Test <t@e.com>\n"
    clean["current_patch"] = clean["patch_input"]
    out = patchwise_graph.invoke(clean)
    assert out["verdict"] == "LGTM"


def test_full_loop_terminates_on_max_rounds() -> None:
    out = patchwise_graph.invoke(_state(max_rounds=1))
    assert out["current_round"] <= 2


def test_soft_interrupt_injects_hint() -> None:
    state = _state()
    state["interrupt_hint"] = "prioritize memory safety"
    out = chanakya_review_node(state)
    assert out["interrupt_hint"] is None
