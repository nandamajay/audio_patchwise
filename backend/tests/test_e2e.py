from fastapi.testclient import TestClient

from app.agents.graph import patchwise_graph
from app.main import app
from app.runtime import SESSION_STORE


def test_e2e_patch_review_loop() -> None:
    client = TestClient(app)

    session_resp = client.post(
        "/session/start",
        json={
            "kernel_version": "6.9",
            "subsystem": "alsa-asoc",
            "source_path": "sound/soc/",
            "llm_model": "gpt-4o",
            "max_rounds": 3,
        },
    )
    assert session_resp.status_code == 200
    session_id = session_resp.json()["session_id"]

    sample_patch = """Subject: fix audio issue

diff --git a/sound/soc/test.c b/sound/soc/test.c
+++ b/sound/soc/test.c
@@ -1,2 +1,3 @@
+\tvoid *ptr = kmalloc(32, GFP_KERNEL);
+return;
"""

    submit_resp = client.post(
        "/patch/submit",
        json={"session_id": session_id, "patch_input": sample_patch},
    )
    assert submit_resp.status_code == 200

    initial_state = SESSION_STORE[session_id]
    out = patchwise_graph.invoke(initial_state)

    assert len(out["review_findings"]) >= 1
    first_round_findings = out["review_findings"][0]["findings"]
    assert any(item["issue_type"] == "STYLE" for item in first_round_findings)

    assert len(out["fix_attempts"]) >= 1
    assert out["verdict"] in {"LGTM", "NEEDS_WORK", "PENDING"}
    assert out["current_round"] <= out["max_rounds"] + 1

    refs = out.get("similar_patches", [])
    assert refs
    assert any("url" in ref and ref["url"] for ref in refs)
