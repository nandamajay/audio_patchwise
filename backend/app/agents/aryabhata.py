from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from typing import Any

from app.agents.state import PatchWiseState
from app.skills.checkpatch_skill import run_checkpatch
from core.llm_factory import get_llm
from core.ssh_pool import AgentRole, ssh_pool
from qgenie_executor import QGenieExecutor

logger = logging.getLogger("uvicorn.error")


class _FallbackAPIClient:
    def __init__(self, provider: str | None, model: str | None):
        self.provider = provider or "qgenie"
        self.model = model or "gpt-4o"

    def analyze(self, task: str, context: str | None = None) -> str:
        llm = get_llm(model=self.model, provider=self.provider, temperature=0.1, streaming=False)
        prompt = f"TASK:\n{task}\n\nCONTEXT:\n{context or ''}\n"
        response = llm.invoke(prompt)
        content = getattr(response, "content", response)
        if isinstance(content, list):
            return "\n".join(str(item) for item in content)
        return str(content or "")


def _ensure_list(state: dict[str, Any], key: str) -> list[Any]:
    value = state.get(key)
    if not isinstance(value, list):
        value = []
        state[key] = value
    return value


def _emit(state: dict[str, Any], payload: dict[str, Any]) -> None:
    if payload.get("agent") in {"chanakya", "aryabhata"}:
        metadata = payload.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        source = (
            payload.get("source")
            or metadata.get("source")
            or state.get("qgenie_last_source_arya")
            or "fallback"
        )
        task_type = (
            payload.get("task_type")
            or metadata.get("task_type")
            or payload.get("type")
            or "validation"
        )
        payload["source"] = source
        payload["task_type"] = task_type
        metadata.setdefault("source", source)
        metadata.setdefault("task_type", task_type)
        payload["metadata"] = metadata
    callback = state.get("_stream_callback")
    if callable(callback):
        callback(payload)


def _emit_tokens(
    state: dict[str, Any],
    agent: str,
    msg_type: str,
    round_id: int,
    text: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    for token in text.split(" "):
        _emit(
            state,
            {
                "agent": agent,
                "type": msg_type,
                "round": round_id,
                "content": token + " ",
                "metadata": metadata or {},
            },
        )


def _parse_checkpatch_issues(output: str) -> list[str]:
    issues: list[str] = []
    for line in (output or "").splitlines():
        if "ERROR:" in line or "WARNING:" in line or "CHECK:" in line:
            issues.append(line.strip())
    return issues


def _parse_approval_token(output: str, patch_hash: str) -> dict[str, Any] | None:
    if not output:
        return None
    token_match = re.search(r"ARYABHATA_APPROVED", output)
    if not token_match:
        return None
    json_match = re.search(r"\{.*\}", output, flags=re.DOTALL)
    if json_match:
        raw = json_match.group(0).replace("'", '"')
        try:
            payload = json.loads(raw)
            if isinstance(payload, dict):
                payload.setdefault("token", "ARYABHATA_APPROVED")
                payload.setdefault("patch_hash", patch_hash)
                return payload
        except Exception:
            pass
    return {
        "token": "ARYABHATA_APPROVED",
        "patch_hash": patch_hash,
    }


def _looks_like_needs_work(text: str) -> bool:
    lowered = (text or "").lower()
    markers = [
        "needs_work",
        "verdict: fail",
        "critical finding",
        "critical_finding",
        '"verdict":"needs_work"',
    ]
    return any(marker in lowered for marker in markers)


def _extract_blockers(text: str) -> list[str]:
    if not text:
        return []
    blockers: list[str] = []
    for line in str(text).splitlines():
        lowered = line.lower()
        if any(k in lowered for k in ["error:", "critical", "needs_work", "must fix", "fail"]):
            blockers.append(line.strip())
        if len(blockers) >= 12:
            break
    return blockers


def _compute_validation_confidence(
    checkpatch_issues: list[str],
    q_symbols: dict[str, Any],
    q_style: dict[str, Any],
    q_approval: dict[str, Any],
    lore_thread: dict[str, Any] | None,
) -> dict[str, Any]:
    blockers: list[str] = []
    blockers.extend(checkpatch_issues[:10])
    blockers.extend(_extract_blockers(q_symbols.get("output", "")))
    blockers.extend(_extract_blockers(q_style.get("output", "")))
    blockers.extend(_extract_blockers(q_approval.get("output", "")))
    deduped: list[str] = []
    for item in blockers:
        if item and item not in deduped:
            deduped.append(item)
    blockers = deduped[:20]

    confidence = 90
    if q_symbols.get("source") != "cli":
        confidence -= 10
    if q_style.get("source") != "cli":
        confidence -= 10
    if q_approval.get("source") != "cli":
        confidence -= 10
    confidence -= min(len(blockers) * 3, 45)
    if lore_thread and lore_thread.get("applied"):
        confidence = max(confidence, 88)
    confidence = max(0, min(100, confidence))
    return {"confidence": confidence, "blockers": blockers}


async def aryabhata_fix_node_async(state: PatchWiseState) -> PatchWiseState:
    """
    ARYABHATA validator node: independently validate CHANAKYA's fixed patch.
    """
    round_id = state.get("current_round", 1)
    session_id = str(state.get("session_id", "") or "")
    current_patch = state.get("current_patch") or state.get("patch_input", "")
    logger.info("[ARYABHATA] preload started at t=0 (lightweight mode)")

    _emit_tokens(
        state,
        "aryabhata",
        "thinking",
        round_id,
        "Running independent symbol/style validation and final approval gate.",
    )

    working_dir: str | None = None
    if session_id:
        try:
            working_dir = await ssh_pool.ensure_work_dir(AgentRole.ARYABHATA, session_id)
        except Exception as exc:
            logger.warning("[ARYABHATA] unable to ensure working dir: %s", exc)

    fallback_client = _FallbackAPIClient(
        provider=state.get("llm_provider"),
        model=state.get("llm_model"),
    )
    qgenie = QGenieExecutor(
        ssh_pool=ssh_pool,
        session_id=session_id,
        fallback_api_client=fallback_client,
    )
    latest_review = state.get("latest_review") if isinstance(state.get("latest_review"), dict) else {}
    issue_summaries = []
    for issue in (latest_review.get("issues") or [])[:8]:
        if isinstance(issue, dict):
            issue_summaries.append(issue.get("error_message", ""))
    chanakya_findings = "; ".join([item for item in issue_summaries if item])[:1200]
    patch_hash = hashlib.sha256(current_patch.encode("utf-8", errors="ignore")).hexdigest()[:12]
    chanakya_token = state.get("approval_token") or state.get("verdict") or "PENDING"
    shared_context = state.get("shared_a2a_context") if isinstance(state.get("shared_a2a_context"), dict) else {}
    if not isinstance(state.get("shared_a2a_context"), dict):
        state["shared_a2a_context"] = shared_context
    chanakya_knowledge = shared_context.get("chanakya_knowledge", {}) if isinstance(shared_context, dict) else {}
    lore_thread = chanakya_knowledge.get("lore_thread_intelligence") if isinstance(chanakya_knowledge, dict) else None

    async def _run_parallel_checks():
        _emit(
            state,
            {
                "agent": "aryabhata",
                "type": "task_start",
                "round": round_id,
                "task_type": "symbols",
                "source": "cli",
                "content": "Running independent symbol/header/dependency validation.",
            },
        )
        _emit(
            state,
            {
                "agent": "aryabhata",
                "type": "task_start",
                "round": round_id,
                "task_type": "style",
                "source": "cli",
                "content": "Running independent kernel coding-style validation.",
            },
        )
        _emit(
            state,
            {
                "agent": "aryabhata",
                "type": "task_start",
                "round": round_id,
                "task_type": "approval",
                "source": "cli",
                "content": "Evaluating final gate verdict and approval token eligibility.",
            },
        )
        return await asyncio.gather(
            qgenie.run(
                agent_name="aryabhata",
                task=(
                    "Perform a full symbol validation pass on this patch. "
                    "Check include headers, out-of-tree references, signatures, and GPL-only symbol usage. "
                    "Return PASS or FAIL with line-by-line findings."
                ),
                context=current_patch,
                working_dir=working_dir,
            ),
            qgenie.run(
                agent_name="aryabhata",
                task=(
                    "Verify full Linux kernel coding-style conformance: tabs, line length, comment style, "
                    "error handling patterns, trailing whitespace. "
                    f"Chanakya findings to validate independently: {chanakya_findings}. "
                    f"Lore thread status: {lore_thread}."
                ),
                context=current_patch,
                working_dir=working_dir,
            ),
            qgenie.run(
                agent_name="aryabhata",
                task=(
                    "You are final gatekeeper before patch submission. "
                    "Return APPROVED or NEEDS_WORK with objective blockers. "
                    "If APPROVED, generate token JSON with token, patch_hash, timestamp, quality_score. "
                    f"Patch hash: {patch_hash}. Chanakya approval status: {chanakya_token}."
                ),
                context=current_patch,
                working_dir=working_dir,
            ),
            return_exceptions=True,
        )

    parallel_results = await _run_parallel_checks()
    q_symbols = parallel_results[0] if isinstance(parallel_results[0], dict) else {"success": False, "source": "fallback", "output": ""}
    q_style = parallel_results[1] if isinstance(parallel_results[1], dict) else {"success": False, "source": "fallback", "output": ""}
    q_approval = parallel_results[2] if isinstance(parallel_results[2], dict) else {"success": False, "source": "fallback", "output": ""}
    _emit(
        state,
        {
            "agent": "aryabhata",
            "type": "task_done",
            "round": round_id,
            "task_type": "symbols",
            "source": q_symbols.get("source", "none"),
            "content": (
                "symbol validation complete"
                if q_symbols.get("success")
                else f"symbol validation degraded ({q_symbols.get('error', 'no_output')})"
            ),
        },
    )
    _emit(
        state,
        {
            "agent": "aryabhata",
            "type": "task_done",
            "round": round_id,
            "task_type": "style",
            "source": q_style.get("source", "none"),
            "content": (
                "style validation complete"
                if q_style.get("success")
                else f"style validation degraded ({q_style.get('error', 'no_output')})"
            ),
        },
    )
    _emit(
        state,
        {
            "agent": "aryabhata",
            "type": "task_done",
            "round": round_id,
            "task_type": "approval",
            "source": q_approval.get("source", "none"),
            "content": (
                "approval gating check complete"
                if q_approval.get("success")
                else f"approval gating degraded ({q_approval.get('error', 'no_output')})"
            ),
        },
    )
    source_votes = [q_symbols.get("source"), q_style.get("source"), q_approval.get("source")]
    source = "cli" if "cli" in source_votes else ("fallback" if "fallback" in source_votes else "none")
    state["qgenie_last_source_arya"] = source
    state["qgenie_working_dir_arya"] = working_dir or ""

    # Keep an explicit independent checkpatch pass.
    checkpatch_result = run_checkpatch(current_patch)
    checkpatch_output = checkpatch_result.get("output", "")
    issues = _parse_checkpatch_issues(checkpatch_output)
    approval_token = _parse_approval_token(q_approval.get("output", ""), patch_hash)

    confidence_payload = _compute_validation_confidence(
        checkpatch_issues=issues,
        q_symbols=q_symbols,
        q_style=q_style,
        q_approval=q_approval,
        lore_thread=lore_thread if isinstance(lore_thread, dict) else None,
    )
    blockers = confidence_payload.get("blockers", [])
    confidence = int(confidence_payload.get("confidence", 0))
    verdict = "LGTM"
    if blockers or _looks_like_needs_work(q_symbols.get("output", "")) or _looks_like_needs_work(q_style.get("output", "")):
        verdict = "NEEDS_WORK"
    if _looks_like_needs_work(q_approval.get("output", "")):
        verdict = "NEEDS_WORK"
    if checkpatch_result.get("status") == "issues" and issues:
        verdict = "NEEDS_WORK"
    if isinstance(lore_thread, dict) and lore_thread.get("applied") and confidence >= 70:
        verdict = "LGTM"
    if approval_token:
        verdict = "LGTM"

    validation_payload = {
        "checkpatch": checkpatch_result,
        "issues": issues,
        "issue_count": len(issues),
        "verdict": verdict,
        "source": source,
        "working_dir": working_dir or "",
        "symbol_validation": q_symbols,
        "style_validation": q_style,
        "approval_validation": q_approval,
        "approval_token": approval_token,
        "confidence": confidence,
        "blockers": blockers,
        "lore_thread_intelligence": lore_thread,
    }

    state["aryabhata_validation"] = validation_payload
    state["verdict"] = verdict
    if approval_token:
        state["approval_token"] = approval_token
    if isinstance(shared_context, dict):
        shared_context["aryabhata_fix_result"] = validation_payload
        shared_context["lgtm"] = verdict == "LGTM"

    _emit(
        state,
        {
            "agent": "aryabhata",
            "type": "aryabhata_validation",
            "round": round_id,
            "content": (
                "Independent validation passed." if verdict == "LGTM" else "Validation found issues to address."
            ),
            "source": source,
            "task_type": "style",
            "metadata": {
                "verdict": verdict,
                "checkpatch": checkpatch_result,
                "issue_count": len(issues),
                "issues": issues[:50],
                "source": source,
                "working_dir": working_dir or "",
                "input_mode": state.get("input_mode", "raw"),
                "symbol_validation": q_symbols,
                "style_validation": q_style,
                "approval_validation": q_approval,
                "token": approval_token,
                "confidence": confidence,
                "blockers": blockers,
                "lore_thread_intelligence": lore_thread,
            },
        },
    )
    if approval_token:
        _emit(
            state,
            {
                "agent": "aryabhata",
                "type": "aryabhata_approval",
                "round": round_id,
                "content": "ARYABHATA approval token generated.",
                "source": source,
                "task_type": "approval",
                "metadata": {"token": approval_token},
            },
        )

    _ensure_list(state, "conversation_log").append(
        {
            "round": round_id,
            "agent": "aryabhata",
            "message": "Validation complete.",
            "validation": validation_payload,
            "source": source,
        }
    )
    logger.info("[ARYABHATA] preload ready before validation; parallel_saved=true")

    max_rounds = int(state.get("max_rounds", 5) or 5)
    if verdict != "LGTM":
        state["current_round"] = min(round_id + 1, max_rounds)
    state["interrupt_hint"] = None
    return state


def aryabhata_fix_node(state: PatchWiseState) -> PatchWiseState:
    """
    Sync wrapper retained for legacy call sites and tests.
    In async paths, call `await aryabhata_fix_node_async(state)` directly.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(aryabhata_fix_node_async(state))
    raise RuntimeError("aryabhata_fix_node() called from running event loop; use aryabhata_fix_node_async()")
