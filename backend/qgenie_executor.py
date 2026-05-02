from __future__ import annotations

import logging
import shlex
import re
import base64
import json
import asyncio
import os
import uuid
from typing import Optional

from core.ssh_pool import AgentRole

logger = logging.getLogger(__name__)

QGENIE_PATH_PREFIX = "export PATH=$HOME/.local/bin:$PATH && "
QGENIE_TIMEOUT = int(os.getenv("PW_QGENIE_TIMEOUT_SECONDS", "300"))  # seconds
QGENIE_RETRY_DELAYS = (2, 4)


class QGenieExecutor:
    """
    Routes agent tasks through the qgenie CLI on dev-compute.
    Uses the shared SSH connection pool. Falls back to HTTP API on failure.
    """

    def __init__(self, ssh_pool, session_id: str = "", fallback_api_client=None):
        self.ssh_pool = ssh_pool
        self.session_id = session_id
        self.fallback = fallback_api_client

    async def run(
        self,
        agent_name: str,  # "chanakya" or "aryabhata"
        task: str,  # natural language task description
        context: Optional[str] = None,  # patch content, file paths, symbols
        working_dir: Optional[str] = None,  # isolated dir on dev-compute
        expect_json: bool = False,
        required_json_keys: Optional[list[str]] = None,
    ) -> dict:
        """
        Execute a qgenie agent task on dev-compute.
        Returns: { "success": bool, "output": str, "source": "cli" | "fallback" | "none" }
        """
        prompt = self._build_prompt(agent_name, task, context)
        cmd = self._build_command(prompt, working_dir)
        role = self._to_role(agent_name)
        session_id = self.session_id or "qgenie-exec"

        attempts = 1 + len(QGENIE_RETRY_DELAYS)
        last_reason = ""
        for attempt in range(1, attempts + 1):
            try:
                result = await self.ssh_pool.exec(
                    agent=role,
                    session_id=session_id,
                    cmd=cmd,
                    timeout=QGENIE_TIMEOUT,
                )
                stdout = (result.stdout or "").strip()
                stderr = (result.stderr or "").strip()
                exit_code = int(result.exit_code or 0)
                cleaned_output = self._clean_cli_output(stdout)

                hard_fail_markers = (
                    "Not inside a trusted directory",
                    "stdin is not a terminal",
                    "Codex execution failed",
                    "Connection error",
                    "Task was destroyed but it is pending",
                )
                looks_failed = any(marker in stdout for marker in hard_fail_markers)
                looks_noisy = self._looks_like_tool_noise(cleaned_output)
                valid_json = True
                parsed_json = None
                if expect_json:
                    parsed_json, valid_json = self._validate_json_output(
                        cleaned_output,
                        required_keys=required_json_keys or [],
                    )

                if (
                    exit_code == 0
                    and cleaned_output
                    and not looks_failed
                    and not looks_noisy
                    and valid_json
                ):
                    logger.info("[%s] qgenie CLI succeeded", agent_name)
                    payload = {
                        "success": True,
                        "output": cleaned_output,
                        "raw_output": stdout,
                        "source": "cli",
                        "stderr": stderr,
                        "exit_code": exit_code,
                        "working_dir": working_dir,
                        "effective_mode": "commit+repo" if working_dir else "raw",
                    }
                    if parsed_json is not None:
                        payload["json"] = parsed_json
                    return payload

                last_reason = stderr or stdout[:400] or "empty_output"
                logger.warning(
                    "[%s] qgenie CLI failed attempt %s/%s (exit=%s): %s",
                    agent_name,
                    attempt,
                    attempts,
                    exit_code,
                    last_reason,
                )
                if attempt < attempts:
                    await asyncio.sleep(QGENIE_RETRY_DELAYS[attempt - 1])
                    continue
            except Exception as exc:
                last_reason = str(exc)
                logger.error(
                    "[%s] SSH exec error attempt %s/%s: %s",
                    agent_name,
                    attempt,
                    attempts,
                    exc,
                )
                if attempt < attempts:
                    await asyncio.sleep(QGENIE_RETRY_DELAYS[attempt - 1])
                    continue
        return self._fallback(agent_name, task, context, last_reason)

    def _to_role(self, agent_name: str) -> AgentRole:
        return AgentRole.CHANAKYA if str(agent_name).lower() == "chanakya" else AgentRole.ARYABHATA

    def _build_prompt(self, agent_name: str, task: str, context: Optional[str]) -> str:
        role_map = {
            "chanakya": (
                "You are Chanakya, an expert Linux kernel patch analyst. "
                "Your job is deep code analysis: checkpatch compliance, "
                "upstream submission requirements, clangd symbol validation, "
                "LORE history research, and commit message quality."
            ),
            "aryabhata": (
                "You are Aryabhata, an expert kernel patch validator. "
                "Your job is validation: symbol lookup, kernel style "
                "verification, cross-tree dependency checking, and "
                "approval gating before submission."
            ),
        }
        role = role_map.get(str(agent_name).lower(), "You are a kernel patch expert.")
        ctx_block = f"\n\nCONTEXT:\n{context}" if context else ""
        return f"{role}\n\nTASK:\n{task}{ctx_block}"

    def _build_command(self, prompt: str, working_dir: Optional[str]) -> str:
        token = uuid.uuid4().hex[:12]
        prompt_file = f"/tmp/pw_qgenie_prompt_{token}.txt"
        last_file = f"/tmp/pw_qgenie_last_{token}.txt"
        stdout_file = f"/tmp/pw_qgenie_stdout_{token}.txt"
        stderr_file = f"/tmp/pw_qgenie_stderr_{token}.txt"
        encoded_prompt = base64.b64encode(prompt.encode("utf-8")).decode("ascii")
        cd_prefix = f"cd {shlex.quote(working_dir)} && " if working_dir else ""
        write_prompt = (
            f"printf %s {shlex.quote(encoded_prompt)} | base64 -d > {shlex.quote(prompt_file)} && "
        )
        run_cmd = (
            "qgenie agent exec --skip-git-repo-check "
            f"--output-last-message {shlex.quote(last_file)} "
            f"\"$(cat {shlex.quote(prompt_file)})\" "
            f"> {shlex.quote(stdout_file)} 2> {shlex.quote(stderr_file)}"
        )
        emit_result = (
            f"cat {shlex.quote(last_file)} 2>/dev/null; "
            f"if [ ! -s {shlex.quote(last_file)} ]; then cat {shlex.quote(stdout_file)} 2>/dev/null; fi; "
            "printf '\\n__PW_QGENIE_EXIT__=%s\\n' \"$ec\"; "
            f"cat {shlex.quote(stderr_file)} 1>&2"
        )
        cleanup = (
            f"rm -f {shlex.quote(prompt_file)} {shlex.quote(last_file)} "
            f"{shlex.quote(stdout_file)} {shlex.quote(stderr_file)}"
        )
        return (
            f"{cd_prefix}{QGENIE_PATH_PREFIX}{write_prompt}"
            f"{run_cmd}; ec=$?; {emit_result}; {cleanup}; exit $ec"
        )

    def _clean_cli_output(self, output: str) -> str:
        text = (output or "").strip()
        if not text:
            return ""

        lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
        lines = [ln for ln in lines if not ln.startswith("WARNING: failed to clean up stale arg0")]
        lines = [ln for ln in lines if not ln.startswith("__PW_QGENIE_EXIT__=")]
        if not lines:
            return ""

        # Extract assistant payload from qgenie agent exec envelope.
        answer_start = None
        for idx, line in enumerate(lines):
            if line.strip().lower() == "qgenie":
                answer_start = idx + 1
                break
        if answer_start is not None and answer_start < len(lines):
            answer_lines = lines[answer_start:]
            token_idx = None
            for idx, line in enumerate(answer_lines):
                if line.strip().lower().startswith("tokens used"):
                    token_idx = idx
                    break
            if token_idx is not None:
                answer_lines = answer_lines[:token_idx]
            candidate = "\n".join(answer_lines).strip()
            candidate = re.split(r"tokens used", candidate, flags=re.IGNORECASE)[0].strip()
            if candidate:
                return candidate

        # Fallback sanitize if envelope markers aren't present.
        scrubbed = []
        for line in lines:
            if re.match(r"^QGenie Agent v", line):
                continue
            if line.strip().lower() in {"user", "mcp startup: no servers"}:
                continue
            if line.startswith("workdir:") or line.startswith("model:") or line.startswith("provider:"):
                continue
            if line.strip() == "--------":
                continue
            scrubbed.append(line)
        candidate = "\n".join(scrubbed).strip()
        candidate = re.split(r"tokens used", candidate, flags=re.IGNORECASE)[0].strip()
        return candidate

    def _looks_like_tool_noise(self, text: str) -> bool:
        lowered = (text or "").lower()
        noisy_markers = (
            "/usr/bin/bash -lc",
            "skill.md",
            "run patchwise patch reviews",
            "qgenie-cli/agent/skills",
            "i'll run the `patchwise` skill workflow",
        )
        return any(marker in lowered for marker in noisy_markers)

    def _validate_json_output(self, text: str, required_keys: list[str]) -> tuple[Optional[dict], bool]:
        if not text:
            return None, False
        parsed: Optional[dict] = None
        try:
            parsed = json.loads(text)
        except Exception:
            first = text.find("{")
            last = text.rfind("}")
            if first >= 0 and last > first:
                try:
                    parsed = json.loads(text[first : last + 1])
                except Exception:
                    return None, False
            else:
                return None, False
        if not isinstance(parsed, dict):
            return None, False
        for key in required_keys:
            if key not in parsed:
                return None, False
        return parsed, True

    def _fallback(self, agent_name: str, task: str, context: Optional[str], reason: str = "") -> dict:
        if self.fallback and hasattr(self.fallback, "analyze"):
            provider = str(getattr(self.fallback, "provider", "") or "").strip().lower()
            if provider in {"qgenie", "qualcomm"} and not str(os.getenv("QGENIE_API_KEY", "")).strip():
                logger.warning("[%s] HTTP fallback skipped: QGENIE_API_KEY missing", agent_name)
                return {
                    "success": False,
                    "output": "",
                    "source": "none",
                    "error": f"{reason}; fallback_skipped=qgenie_key_missing",
                }
            try:
                logger.info("[%s] Using HTTP API fallback", agent_name)
                result = self.fallback.analyze(task, context)
                return {
                    "success": True,
                    "output": str(result or ""),
                    "source": "fallback",
                    "error": reason,
                }
            except Exception as exc:
                logger.error("[%s] Fallback analyze failed: %s", agent_name, exc)
                return {
                    "success": False,
                    "output": "",
                    "source": "none",
                    "error": f"{reason}; fallback_error={exc}",
                }
        return {"success": False, "output": "", "source": "none", "error": reason}
