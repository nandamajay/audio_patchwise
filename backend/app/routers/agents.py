from __future__ import annotations

import asyncio
import traceback

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.agents.aryabhata import aryabhata_fix_node
from app.agents.chanakya import chanakya_review_node
from app.knowledge.sql_store import PatchSQLStore
from app.knowledge.vector_store import PatchVectorStore
from app.runtime import REPORT_STORE, SESSION_STORE, connection_manager
try:
    from api.dependencies import session_manager
except Exception:  # pragma: no cover
    session_manager = None

router = APIRouter(tags=["agents"])
RUN_TASKS: dict[str, asyncio.Task] = {}


def _list_or_empty(value):
    return value if isinstance(value, list) else []


def _normalize_state(state: dict) -> dict:
    if not isinstance(state, dict):
        return {}

    for key in (
        "review_findings",
        "fix_attempts",
        "similar_patches",
        "conversation_log",
        "messages",
        "fix_history",
        "current_issues",
        "a2a_messages",
        "touched_lines",
    ):
        if not isinstance(state.get(key), list):
            state[key] = []

    if not isinstance(state.get("latest_review"), dict):
        state["latest_review"] = {}

    patch_input = state.get("patch_input")
    if isinstance(patch_input, dict):
        patch_input = patch_input.get("raw_text", "")
    if patch_input is None:
        patch_input = ""
    if not isinstance(patch_input, str):
        patch_input = str(patch_input)
    state["patch_input"] = patch_input

    current_patch = state.get("current_patch")
    if current_patch is None:
        current_patch = ""
    if not isinstance(current_patch, str):
        current_patch = str(current_patch)
    if not current_patch:
        current_patch = patch_input
    state["current_patch"] = current_patch

    current_fixed_patch = state.get("current_fixed_patch")
    if current_fixed_patch is not None and not isinstance(current_fixed_patch, str):
        current_fixed_patch = str(current_fixed_patch)
    state["current_fixed_patch"] = current_fixed_patch

    max_rounds = state.get("max_rounds", 5)
    if not isinstance(max_rounds, int) or max_rounds <= 0:
        max_rounds = 5
    state["max_rounds"] = max_rounds

    current_round = state.get("current_round", 1)
    if not isinstance(current_round, int) or current_round <= 0:
        current_round = 1
    state["current_round"] = current_round

    if not state.get("llm_provider"):
        state["llm_provider"] = "qgenie"
    if not state.get("llm_model"):
        state["llm_model"] = "gpt-4o"
    challenge_timeout = state.get("challenge_timeout", 60)
    if not isinstance(challenge_timeout, int) or challenge_timeout < 10:
        challenge_timeout = 60
    state["challenge_timeout"] = challenge_timeout

    shared = state.get("shared_a2a_context")
    if not isinstance(shared, dict):
        shared = {}
    shared.setdefault("session_id", state.get("session_id", ""))
    shared.setdefault("original_patch", patch_input)
    shared.setdefault("current_patch", current_patch)
    shared.setdefault("round_number", state["current_round"])
    shared.setdefault("negotiation_threads", {})
    shared.setdefault("all_messages", [])
    shared.setdefault("touched_lines", state.get("touched_lines", []))
    shared.setdefault("impact_radius", {})
    shared.setdefault("chanakya_knowledge", {})
    shared.setdefault("aryabhata_fix_result", None)
    shared.setdefault("user_arbitration_pending", False)
    shared.setdefault("lgtm", False)
    shared.setdefault("challenge_timeout", challenge_timeout)
    state["shared_a2a_context"] = shared
    return state


def _hydrate_session_from_persistent_store(session_id: str) -> None:
    if session_id in SESSION_STORE or session_manager is None:
        return

    snapshot = session_manager.get_session(session_id)
    if not snapshot:
        return

    patch_input = snapshot.patch_input or {}
    patch_text = (
        patch_input.get("raw_text")
        or patch_input.get("file_path", "")
        or patch_input.get("gerrit_url", "")
        or patch_input.get("lkml_url", "")
    )

    review_report = snapshot.review_report or {}

    SESSION_STORE[session_id] = _normalize_state(
        {
            "session_id": session_id,
            "patch_input": patch_text,
            "kernel_version": snapshot.context.get("kernel_version", "unknown"),
            "subsystem": snapshot.context.get("subsystem", "alsa-asoc"),
            "source_path": snapshot.context.get("source_path", ""),
            "llm_provider": snapshot.config.get("llm_provider", "qgenie"),
            "llm_model": snapshot.config.get("llm_model", "gpt-4o"),
            "max_rounds": snapshot.max_rounds or snapshot.config.get("max_rounds", 5),
            "current_round": max(1, snapshot.current_round or 1),
            "review_findings": _list_or_empty(review_report.get("review_findings")),
            "fix_attempts": _list_or_empty(review_report.get("fix_attempts")),
            "similar_patches": _list_or_empty(review_report.get("similar_patches")),
            "current_patch": snapshot.final_patch or patch_text,
            "verdict": snapshot.verdict or "PENDING",
            "interrupt_hint": None,
            "conversation_log": _list_or_empty(snapshot.conversation),
            "quality_score": review_report.get("quality_score", 0.0),
            "messages": [],
        }
    )


def _stream_callback_for(loop: asyncio.AbstractEventLoop, session_id: str):
    def _callback(payload: dict) -> None:
        asyncio.run_coroutine_threadsafe(
            connection_manager.broadcast(session_id, payload),
            loop,
        )

    return _callback


def _execute_review_cycle_sync(state: dict) -> dict:
    """
    Execute CHANAKYA -> ARYABHATA loop directly to avoid langgraph runtime
    sync/async compatibility issues in websocket flow.
    """
    while True:
        state = asyncio.run(chanakya_review_node(state))
        state = _normalize_state(state)

        shared = state.get("shared_a2a_context")
        if isinstance(shared, dict) and shared.get("user_arbitration_pending"):
            return state

        if state.get("verdict") == "LGTM":
            return state

        if state.get("current_round", 1) >= state.get("max_rounds", 5):
            return state

        state = aryabhata_fix_node(state)
        state = _normalize_state(state)


async def run_agent_loop(session_id: str) -> None:
    state = SESSION_STORE.get(session_id)
    if not state:
        return

    state = _normalize_state(state)

    loop = asyncio.get_running_loop()
    state["_stream_callback"] = _stream_callback_for(loop, session_id)
    SESSION_STORE[session_id] = state

    if session_manager:
        try:
            session_manager.update_session(
                session_id,
                status="running",
                current_round=state.get("current_round", 1),
            )
        except Exception:
            pass

    try:
        final_state = await asyncio.to_thread(_execute_review_cycle_sync, state)
    except Exception as exc:
        error_text = traceback.format_exc(limit=6)
        await connection_manager.broadcast(
            session_id,
            {
                "agent": "system",
                "type": "error",
                "round": state.get("current_round", 1),
                "content": f"Agent loop failed: {exc}",
                "metadata": {"traceback": error_text},
            },
        )
        state["verdict"] = "NEEDS_WORK"
        state.setdefault("conversation_log", []).append(
            {
                "agent": "system",
                "message": f"Agent loop failed: {exc}",
                "traceback": error_text,
            }
        )
        state.pop("_stream_callback", None)
        SESSION_STORE[session_id] = state
        if session_manager:
            try:
                session_manager.update_session(
                    session_id,
                    status="failed",
                    current_round=state.get("current_round", 1),
                    verdict=state.get("verdict", "NEEDS_WORK"),
                    final_patch=state.get("current_patch", ""),
                    conversation=state.get("conversation_log", []),
                    review_report={
                        "review_findings": state.get("review_findings", []),
                        "fix_attempts": state.get("fix_attempts", []),
                        "similar_patches": state.get("similar_patches", []),
                        "quality_score": state.get("quality_score", 0.0),
                    },
                )
            except Exception:
                pass
        return
    final_state = _normalize_state(final_state)
    final_state.pop("_stream_callback", None)
    SESSION_STORE[session_id] = final_state

    try:
        PatchVectorStore(collection_name="patchwise_alsa_asoc").update_from_session(
            final_state
        )
        PatchSQLStore().update_from_session(final_state)
    except Exception:
        # Keep runtime path resilient when optional local DB/vector deps are unavailable.
        pass

    REPORT_STORE[session_id] = {
        "session_id": session_id,
        "verdict": final_state.get("verdict", "PENDING"),
        "quality_score": final_state.get("quality_score", 0.0),
        "rounds": final_state.get("current_round", 1),
        "review_findings": final_state.get("review_findings", []),
        "fix_attempts": final_state.get("fix_attempts", []),
        "similar_patches": final_state.get("similar_patches", []),
    }

    if session_manager:
        try:
            session_manager.update_session(
                session_id,
                status="completed",
                current_round=final_state.get("current_round", 1),
                verdict=final_state.get("verdict", "PENDING"),
                final_patch=final_state.get("current_patch", ""),
                conversation=final_state.get("conversation_log", []),
                review_report={
                    "review_findings": final_state.get("review_findings", []),
                    "fix_attempts": final_state.get("fix_attempts", []),
                    "similar_patches": final_state.get("similar_patches", []),
                    "quality_score": final_state.get("quality_score", 0.0),
                },
            )
        except Exception:
            pass

    await connection_manager.broadcast(
        session_id,
        {
            "agent": "chanakya",
            "type": "lgtm" if final_state.get("verdict") == "LGTM" else "verdict",
            "round": final_state.get("current_round", 1),
            "content": "✅ LGTM — CHANAKYA approves the patch!"
            if final_state.get("verdict") == "LGTM"
            else "Review loop completed at max rounds.",
            "metadata": {
                "verdict": final_state.get("verdict"),
                "quality_score": final_state.get("quality_score"),
            },
        },
    )


@router.websocket("/ws/agent-stream/{session_id}")
@router.websocket("/ws/{session_id}")
async def agent_stream(websocket: WebSocket, session_id: str) -> None:
    _hydrate_session_from_persistent_store(session_id)
    if session_id in SESSION_STORE:
        SESSION_STORE[session_id] = _normalize_state(SESSION_STORE[session_id])
    await connection_manager.connect(session_id, websocket)
    try:
        await connection_manager.broadcast(
            session_id,
            {
                "agent": "system",
                "type": "thinking",
                "round": SESSION_STORE.get(session_id, {}).get("current_round", 1),
                "content": "Agent stream connected.",
                "metadata": {},
            },
        )

        if session_id in SESSION_STORE and SESSION_STORE[session_id].get("patch_input"):
            running = RUN_TASKS.get(session_id)
            if running is None or running.done():
                RUN_TASKS[session_id] = asyncio.create_task(run_agent_loop(session_id))

        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            if msg_type == "interrupt":
                hint = data.get("hint", "")
                if session_id in SESSION_STORE:
                    SESSION_STORE[session_id]["interrupt_hint"] = hint
                await connection_manager.broadcast(
                    session_id,
                    {
                        "agent": "system",
                        "type": "thinking",
                        "round": SESSION_STORE.get(session_id, {}).get("current_round", 1),
                        "content": "Soft interrupt captured.",
                        "metadata": {"hint": hint},
                    },
                )
            elif msg_type == "start":
                _hydrate_session_from_persistent_store(session_id)
                if session_id in SESSION_STORE:
                    SESSION_STORE[session_id] = _normalize_state(SESSION_STORE[session_id])
                    running = RUN_TASKS.get(session_id)
                    if running is None or running.done():
                        RUN_TASKS[session_id] = asyncio.create_task(run_agent_loop(session_id))
            elif msg_type == "update_config":
                if session_id in SESSION_STORE:
                    seconds = data.get("challenge_timeout")
                    try:
                        seconds = int(seconds)
                    except Exception:
                        seconds = None
                    if isinstance(seconds, int) and 10 <= seconds <= 300:
                        SESSION_STORE[session_id]["challenge_timeout"] = seconds
                        shared = SESSION_STORE[session_id].get("shared_a2a_context")
                        if isinstance(shared, dict):
                            shared["challenge_timeout"] = seconds
                        await connection_manager.broadcast(
                            session_id,
                            {
                                "agent": "system",
                                "type": "config_update",
                                "round": SESSION_STORE[session_id].get("current_round", 1),
                                "content": f"Challenge timeout updated to {seconds}s.",
                                "metadata": {"challenge_timeout": seconds},
                            },
                        )
            elif msg_type == "arbitration_decision":
                if session_id in SESSION_STORE:
                    issue_id = data.get("issue_id")
                    decision = data.get("decision")
                    shared = SESSION_STORE[session_id].get("shared_a2a_context")
                    if isinstance(shared, dict):
                        shared["user_arbitration_pending"] = False
                        shared["last_arbitration_decision"] = {
                            "issue_id": issue_id,
                            "decision": decision,
                        }
                    await connection_manager.broadcast(
                        session_id,
                        {
                            "agent": "system",
                            "type": "arbitration_resolved",
                            "round": SESSION_STORE[session_id].get("current_round", 1),
                            "content": f"Arbitration resolved for issue {issue_id}: {decision}",
                            "metadata": {"issue_id": issue_id, "decision": decision},
                        },
                    )
            else:
                await connection_manager.broadcast(
                    session_id,
                    {
                        "agent": "system",
                        "type": "thinking",
                        "round": SESSION_STORE.get(session_id, {}).get("current_round", 1),
                        "content": "Unsupported message type ignored.",
                        "metadata": {"received": msg_type},
                    },
                )
    except WebSocketDisconnect:
        await connection_manager.disconnect(session_id, websocket)
