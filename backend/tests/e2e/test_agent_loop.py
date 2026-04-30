from fastapi.testclient import TestClient

from app.main import app
from app.runtime import SESSION_STORE


def test_full_session_via_api_with_mock_llm() -> None:
    client = TestClient(app)
    start = client.post(
        "/session/start",
        json={
            "kernel_version": "6.9",
            "subsystem": "alsa-asoc",
            "source_path": "sound/soc/",
            "llm_model": "mock",
            "max_rounds": 2,
        },
    )
    assert start.status_code == 200
    session_id = start.json()["session_id"]

    submit = client.post(
        "/patch/submit",
        json={"session_id": session_id, "patch_input": "Subject: fix\n+\tint x;\n"},
    )
    assert submit.status_code == 200


def test_websocket_streaming_delivers_tokens() -> None:
    client = TestClient(app)
    start = client.post(
        "/session/start",
        json={
            "kernel_version": "6.9",
            "subsystem": "alsa-asoc",
            "source_path": "sound/soc/",
            "llm_model": "mock",
            "max_rounds": 2,
        },
    )
    session_id = start.json()["session_id"]
    client.post(
        "/patch/submit",
        json={"session_id": session_id, "patch_input": "Subject: fix\n+\tint x;\n"},
    )

    with client.websocket_connect(f"/ws/agent-stream/{session_id}") as ws:
        ws.send_json({"type": "start"})
        msg = ws.receive_json()
        assert "type" in msg


def test_session_persists_to_sqlite() -> None:
    client = TestClient(app)
    start = client.post(
        "/session/start",
        json={
            "kernel_version": "6.9",
            "subsystem": "alsa-asoc",
            "source_path": "sound/soc/",
            "llm_model": "mock",
            "max_rounds": 2,
        },
    )
    session_id = start.json()["session_id"]
    assert session_id in SESSION_STORE
