from app.agents.aryabhata import aryabhata_fix_node


def test_aryabhata_applies_fixes_and_advances_round() -> None:
    state = {
        "session_id": "s1",
        "patch_input": "+\tint x = kmalloc(16, GFP_KERNEL);\n",
        "kernel_version": "6.9",
        "subsystem": "alsa-asoc",
        "source_path": "sound/soc/",
        "llm_model": "gpt-4o",
        "max_rounds": 5,
        "current_round": 1,
        "review_findings": [
            {
                "round": 1,
                "findings": [
                    {
                        "issue_type": "STYLE",
                        "severity": "WARNING",
                        "line_number": 1,
                        "description": "Tab detected",
                        "suggestion": "Replace tabs",
                        "similar_patch_refs": [],
                    }
                ],
            }
        ],
        "fix_attempts": [],
        "similar_patches": [],
        "current_patch": "+\tint x = kmalloc(16, GFP_KERNEL);\n",
        "verdict": "NEEDS_WORK",
        "interrupt_hint": None,
        "conversation_log": [],
        "quality_score": 40.0,
        "messages": [],
    }

    out = aryabhata_fix_node(state)
    assert out["current_round"] == 2
    assert len(out["fix_attempts"]) == 1
    assert "\t" not in out["current_patch"]
