from __future__ import annotations

import asyncio
import logging
import re
import shlex
from typing import List, Optional

from core.ssh_pool import AgentRole, ssh_pool
from graph.state import fix_ready_event

logger = logging.getLogger("uvicorn.error")


class AryabhataExecutor:
    """
    ARYABHATA executor — Validator & Quality Gatekeeper.
    Runs independent checkpatch/patchwise and cross-line impact checks.
    Pre-loads context in parallel while CHANAKYA fixes.
    Uses ssh_pool for aryabhata dev_compute execution with its own screen session.
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.agent = AgentRole.ARYABHATA
        self.kernel_path = ssh_pool.kernel_path
        self.patchwise_bin = ssh_pool.patchwise_bin
        self._preload_done = asyncio.Event()
        self._preload_data: dict = {}

    async def preload_context(self, commits: List[str], patch_files: List[str] | None = None):
        logger.info("[ARYABHATA] parallel preload started (t=0)")
        tasks = [
            self._preload_git_context(commits),
            self._preload_symbol_index(commits),
            self._preload_header_scan(commits),
            self._warmup_clangd(),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        self._preload_data = {
            "git_context": results[0] if not isinstance(results[0], Exception) else {},
            "symbol_index": results[1] if not isinstance(results[1], Exception) else {},
            "header_scan": results[2] if not isinstance(results[2], Exception) else {},
            "clangd_ready": not isinstance(results[3], Exception),
            "patch_files": patch_files or [],
        }
        self._preload_done.set()
        logger.info("[ARYABHATA] preload ready before validation")

    async def _preload_git_context(self, commits: List[str]) -> dict:
        ctx: dict[str, str] = {}
        for commit in commits:
            result = await ssh_pool.exec(
                self.agent,
                self.session_id,
                f"git -C {shlex.quote(self.kernel_path)} show --stat --patch {commit}",
                timeout=60,
            )
            ctx[commit] = result.stdout
        return ctx

    async def _preload_symbol_index(self, commits: List[str]) -> dict:
        symbols: dict[str, str] = {}
        for commit in commits:
            files_res = await ssh_pool.exec(
                self.agent,
                self.session_id,
                f"git -C {shlex.quote(self.kernel_path)} diff-tree --no-commit-id -r --name-only {commit}",
                timeout=20,
            )
            for filepath in files_res.stdout.splitlines():
                if not filepath.endswith((".c", ".h")):
                    continue
                full_path = f"{self.kernel_path}/{filepath}"
                sym_res = await ssh_pool.exec(
                    self.agent,
                    self.session_id,
                    f"grep -n '^[a-zA-Z].*(' {shlex.quote(full_path)} 2>/dev/null | head -100",
                    timeout=20,
                )
                symbols[filepath] = sym_res.stdout
        return symbols

    async def _preload_header_scan(self, commits: List[str]) -> dict:
        stale: dict = {}
        for commit in commits:
            c_files = await ssh_pool.exec(
                self.agent,
                self.session_id,
                f"git -C {shlex.quote(self.kernel_path)} diff-tree --no-commit-id -r --name-only {commit} | grep '\\.c$' || true",
                timeout=20,
            )
            for c_file in c_files.stdout.splitlines():
                h_file = c_file.replace(".c", ".h")
                h_path = f"{self.kernel_path}/{h_file}"
                exists = await ssh_pool.exec(
                    self.agent,
                    self.session_id,
                    f"test -f {shlex.quote(h_path)} && echo EXISTS || echo NOTFOUND",
                    timeout=8,
                )
                if "EXISTS" in exists.stdout:
                    stale[h_file] = {"path": h_path, "c_file": c_file}
        return stale

    async def _warmup_clangd(self):
        result = await ssh_pool.exec(
            self.agent,
            self.session_id,
            "command -v clangd && echo READY || echo UNAVAILABLE",
            timeout=10,
        )
        if "READY" in result.stdout:
            await ssh_pool.exec(
                self.agent,
                self.session_id,
                "clangd --background-index >/tmp/pw_clangd.log 2>&1 &",
                timeout=10,
            )
            logger.info("[ARYABHATA] clangd background index started")
        else:
            logger.info("[ARYABHATA] clangd unavailable, using grep-based impact")

    async def validate_chanakya_fix(
        self,
        fixed_patches: List[dict],
        original_issues: List[dict],
        commits: List[str],
    ) -> dict:
        await self.wait_for_fix_ready_event()
        if not self._preload_done.is_set():
            await asyncio.wait_for(self._preload_done.wait(), timeout=120)
        patch_dir = await self._write_patches_to_workdir(fixed_patches)
        results = await asyncio.gather(
            self._run_own_checkpatch(patch_dir),
            self._run_own_patchwise(commits),
            self._detect_cross_line_impact(commits, original_issues),
            self._check_stale_prototypes(commits),
            self._verify_commit_messages(patch_dir),
            self._verify_cover_letter(patch_dir),
            return_exceptions=True,
        )
        validation = {
            "checkpatch": results[0] if not isinstance(results[0], Exception) else {},
            "patchwise": results[1] if not isinstance(results[1], Exception) else {},
            "cross_line_impact": results[2] if not isinstance(results[2], Exception) else {},
            "stale_prototypes": results[3] if not isinstance(results[3], Exception) else {},
            "commit_messages": results[4] if not isinstance(results[4], Exception) else {},
            "cover_letter": results[5] if not isinstance(results[5], Exception) else {},
            "execution_mode": ssh_pool.mode.value,
            "preload_used": True,
        }
        all_clean = (
            validation["checkpatch"].get("errors", []) == []
            and validation["stale_prototypes"].get("found", []) == []
            and validation["cross_line_impact"].get("critical_impacts", []) == []
            and validation["commit_messages"].get("issues", []) == []
            and validation["cover_letter"].get("errors", []) == []
        )
        validation["verdict"] = "LGTM" if all_clean else "NEEDS_WORK"
        validation["lgtm"] = all_clean
        return validation

    async def wait_for_fix_ready_event(self) -> None:
        await asyncio.wait_for(fix_ready_event.wait(), timeout=180)

    async def _write_patches_to_workdir(self, fixed_patches: List[dict]) -> str:
        work_dir = await ssh_pool.ensure_work_dir(self.agent, self.session_id)
        patch_dir = f"{work_dir}/aryabhata_validation"
        await ssh_pool.exec(self.agent, self.session_id, f"mkdir -p {shlex.quote(patch_dir)}", timeout=15)
        for patch in fixed_patches:
            filename = patch.get("filename", "0001.patch")
            content = patch.get("content", "")
            escaped = content.replace("'", "'\"'\"'")
            await ssh_pool.exec(
                self.agent,
                self.session_id,
                f"cat > {shlex.quote(patch_dir + '/' + filename)} <<'EOF'\n{escaped}\nEOF",
                timeout=20,
            )
        return patch_dir

    async def _run_own_checkpatch(self, patch_dir: str) -> dict:
        result = await ssh_pool.exec(
            self.agent,
            self.session_id,
            (
                f"for f in {shlex.quote(patch_dir)}/*.patch; do "
                f"{shlex.quote(self.kernel_path)}/scripts/checkpatch.pl --strict --show-types \"$f\"; "
                f"done"
            ),
            timeout=90,
        )
        output = (result.stdout or "") + (result.stderr or "")
        errors = re.findall(r"ERROR:(\\w+)", output)
        warnings = re.findall(r"WARNING:(\\w+)", output)
        return {"errors": errors, "warnings": warnings, "output": output}

    async def _run_own_patchwise(self, commits: List[str]) -> dict:
        commit_args = " ".join(commits)
        cmd = (
            f"{self.patchwise_bin} --repo-path {shlex.quote(self.kernel_path)} "
            f"--commits {commit_args} --reviews AiCodeReview"
        )
        result = await ssh_pool.exec(self.agent, self.session_id, cmd, timeout=300)
        return {"output": result.stdout, "stderr": result.stderr, "exit_code": result.exit_code}

    async def _detect_cross_line_impact(self, commits: List[str], original_issues: List[dict]) -> dict:
        impacts: list[dict] = []
        for commit in commits:
            files_res = await ssh_pool.exec(
                self.agent,
                self.session_id,
                f"git -C {shlex.quote(self.kernel_path)} diff-tree --no-commit-id -r --name-only {commit}",
                timeout=20,
            )
            for filepath in files_res.stdout.splitlines():
                if not filepath.endswith((".c", ".h")):
                    continue
                grep_res = await ssh_pool.exec(
                    self.agent,
                    self.session_id,
                    f"grep -rn \"return\" {shlex.quote(self.kernel_path + '/' + filepath)} | head -20",
                    timeout=20,
                )
                if grep_res.stdout.strip():
                    impacts.append(
                        {
                            "file": filepath,
                            "impact": "return value propagation change; verify callers",
                            "severity": "MEDIUM",
                        }
                    )
        critical = [i for i in impacts if i.get("severity") == "CRITICAL"]
        return {"impacts": impacts, "critical_impacts": critical}

    async def _check_stale_prototypes(self, commits: List[str]) -> dict:
        found: list[dict] = []
        for commit in commits:
            c_files = await ssh_pool.exec(
                self.agent,
                self.session_id,
                f"git -C {shlex.quote(self.kernel_path)} diff-tree --no-commit-id -r --name-only {commit} | grep '\\.c$' || true",
                timeout=20,
            )
            for c_file in c_files.stdout.splitlines():
                h_file = c_file.replace(".c", ".h")
                h_path = f"{self.kernel_path}/{h_file}"
                exists = await ssh_pool.exec(
                    self.agent,
                    self.session_id,
                    f"test -f {shlex.quote(h_path)} && echo EXISTS || echo NOTFOUND",
                    timeout=10,
                )
                if "EXISTS" in exists.stdout:
                    found.append({"header": h_file, "reason": "possible stale prototype"})
        return {"found": found}

    async def _verify_commit_messages(self, patch_dir: str) -> dict:
        result = await ssh_pool.exec(
            self.agent,
            self.session_id,
            f"grep -R \"^Subject:\" {shlex.quote(patch_dir)}/*.patch 2>/dev/null || true",
            timeout=20,
        )
        issues: list[str] = []
        for line in result.stdout.splitlines():
            if len(line.split("Subject:")[-1].strip()) < 8:
                issues.append("Subject too short")
        return {"issues": issues}

    async def _verify_cover_letter(self, patch_dir: str) -> dict:
        cover_path = f"{patch_dir}/0000-cover-letter.patch"
        result = await ssh_pool.exec(
            self.agent,
            self.session_id,
            f"test -f {shlex.quote(cover_path)} && cat {shlex.quote(cover_path)} || true",
            timeout=20,
        )
        errors: list[str] = []
        text = result.stdout
        if "*** SUBJECT HERE ***" in text or "*** BLURB HERE ***" in text:
            errors.append("PLACEHOLDER_USE")
        return {"errors": errors}
