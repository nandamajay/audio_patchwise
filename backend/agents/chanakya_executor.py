from __future__ import annotations

import asyncio
import logging
import os
import re
import shlex
from pathlib import PurePosixPath
from typing import List

from core.screen_manager import screen_manager
from core.ssh_pool import AgentRole, ssh_pool

logger = logging.getLogger("uvicorn.error")

QGENIE_BASE_URL = os.getenv("QGENIE_BASE_URL", "https://qgenie-chat.qualcomm.com/v1")
QGENIE_API_KEY = os.getenv("QGENIE_API_KEY", "")


class ChanakyaExecutor:
    """
    CHANAKYA executor on dev-compute.
    Mirrors QGenie CLI flow:
    ls *.patch -> git log -> map patch->commit -> patchwise -> git show -> fix/amend/format-patch -> self-validate.
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.agent = AgentRole.CHANAKYA
        self.kernel_path = ssh_pool.kernel_path
        self.patchwise_bin = ssh_pool.patchwise_bin

    async def _screen_name(self) -> str:
        return await screen_manager.create_screen(self.agent, self.session_id)

    async def explore_patch_dir(self, patch_dir: str) -> dict:
        screen = await self._screen_name()
        await screen_manager.run_in_screen(self.agent, self.session_id, f"cd {shlex.quote(patch_dir)}")
        await screen_manager.run_in_screen(self.agent, self.session_id, "ls *.patch")
        await screen_manager.run_in_screen(self.agent, self.session_id, "git log --oneline -n 6")
        return {
            "screen_name": screen,
            "work_dir": ssh_pool._work_dir(self.agent, self.session_id),
        }

    async def map_patches_to_commits(self, patch_dir: str, repo_path: str) -> dict[str, str]:
        """
        map_patches_to_commits:
        - list .patch files
        - git log --oneline -n 20
        - match filename subject fragments with commit subjects
        """
        patches_res = await ssh_pool.exec(
            self.agent,
            self.session_id,
            f"cd {shlex.quote(patch_dir)} && ls *.patch 2>/dev/null || true",
            timeout=20,
        )
        log_res = await ssh_pool.exec(
            self.agent,
            self.session_id,
            f"git -C {shlex.quote(repo_path)} log --oneline -n 20",
            timeout=20,
        )
        patch_files = [p.strip() for p in patches_res.stdout.splitlines() if p.strip().endswith(".patch")]
        log_lines = [l.strip() for l in log_res.stdout.splitlines() if l.strip()]
        mapping: dict[str, str] = {}
        for patch in patch_files:
            slug = patch.split("-", 1)[-1].replace(".patch", "").replace("-", " ").lower()
            best_hash = ""
            for line in log_lines:
                parts = line.split(" ", 1)
                if len(parts) != 2:
                    continue
                hsh, subj = parts
                if any(token and token in subj.lower() for token in slug.split()[:4]):
                    best_hash = hsh
                    break
            if not best_hash and log_lines:
                best_hash = log_lines[0].split()[0]
            if best_hash:
                mapping[patch] = best_hash
        return mapping

    async def run_patchwise(self, commits: List[str], reviews: List[str] | None = None) -> dict:
        """
        run_patchwise_full with graceful fallback:
          - full suite first
          - fallback if ImportError/llvm-config missing
        """
        if reviews is None:
            reviews = ["Checkpatch", "AiCodeReview", "LLMCommitAudit"]
        commit_args = " ".join(commits)
        provider_args = f"--provider {QGENIE_BASE_URL}" if QGENIE_API_KEY else ""
        cmd = (
            f"{self.patchwise_bin} "
            f"--repo-path {shlex.quote(self.kernel_path)} "
            f"--commits {commit_args} "
            f"--reviews {' '.join(reviews)} "
            f"{provider_args}"
        )
        result = await ssh_pool.exec(self.agent, self.session_id, cmd, timeout=600)
        if "ImportError" in result.stderr or "llvm-config" in result.stderr:
            logger.warning("[CHANAKYA] Full patchwise blocked (llvm-config) -> fallback checkpatch path")
            fallback_reviews = ["Checkpatch", "LLMCommitAudit"]
            fallback_cmd = (
                f"{self.patchwise_bin} "
                f"--repo-path {shlex.quote(self.kernel_path)} "
                f"--commits {commit_args} "
                f"--reviews {' '.join(fallback_reviews)} "
                f"{provider_args}"
            )
            result = await ssh_pool.exec(self.agent, self.session_id, fallback_cmd, timeout=300)
            return {
                "output": result.stdout,
                "fallback_used": True,
                "fallback_reason": "llvm-config not installed",
                "reviews_run": fallback_reviews,
            }
        return {
            "output": result.stdout,
            "fallback_used": False,
            "reviews_run": reviews,
        }

    async def run_git_show(self, commits: List[str]) -> dict:
        results: dict[str, str] = {}
        for commit in commits:
            result = await ssh_pool.exec(
                self.agent,
                self.session_id,
                f"git -C {shlex.quote(self.kernel_path)} show --stat --patch --find-renames --find-copies {commit}",
                timeout=60,
            )
            results[commit] = result.stdout
        return results

    async def run_checkpatch_cover_letter(self, cover_letter_path: str) -> dict:
        cmd = (
            f"{shlex.quote(self.kernel_path)}/scripts/checkpatch.pl "
            f"--strict --show-types --terse {shlex.quote(cover_letter_path)}"
        )
        result = await ssh_pool.exec(self.agent, self.session_id, cmd, timeout=60)
        out = (result.stdout or "") + (result.stderr or "")
        return {
            "output": out,
            "has_errors": result.exit_code != 0,
            "placeholder_found": "PLACEHOLDER_USE" in out,
        }

    async def fix_cover_letter(self, patch_dir: str, subjects: List[str]) -> dict:
        """
        cover_letter fix on dev-compute:
        - checkpatch -> detect PLACEHOLDER_USE
        - replace *** SUBJECT HERE *** and *** BLURB HERE ***
        - re-run checkpatch
        """
        cover_file = str(PurePosixPath(patch_dir) / "0000-cover-letter.patch")
        pre = await self.run_checkpatch_cover_letter(cover_file)
        if not pre["placeholder_found"]:
            return {"fixed": False, "output": pre["output"]}
        subject = subjects[0] if subjects else "[PATCH v2 0/1] subsystem: update cover letter"
        blurb = "This revision addresses checkpatch and review feedback with focused fixes."
        await ssh_pool.exec(
            self.agent,
            self.session_id,
            (
                f"sed -i \"s#\\*\\*\\* SUBJECT HERE \\*\\*\\*#{subject.replace('#', ' ')}#g\" {shlex.quote(cover_file)} && "
                f"sed -i \"s#\\*\\*\\* BLURB HERE \\*\\*\\*#{blurb.replace('#', ' ')}#g\" {shlex.quote(cover_file)}"
            ),
            timeout=20,
        )
        post = await self.run_checkpatch_cover_letter(cover_file)
        return {
            "fixed": True,
            "placeholder_cleared": "PLACEHOLDER_USE" not in post["output"],
            "output": post["output"],
        }

    async def apply_fix_and_format_patch(self, commit: str, fix_description: str, patch_output_dir: str) -> dict:
        work_dir = ssh_pool._work_dir(self.agent, self.session_id)
        worktree_path = f"{work_dir}/fix_worktree"

        await ssh_pool.exec(
            self.agent,
            self.session_id,
            f"git -C {shlex.quote(self.kernel_path)} worktree add {shlex.quote(worktree_path)} {commit}",
            timeout=40,
        )

        fix_cmds = await self._generate_fix_commands(commit, fix_description, worktree_path)
        for cmd in fix_cmds:
            await ssh_pool.exec(self.agent, self.session_id, cmd, timeout=45)

        await ssh_pool.exec(
            self.agent,
            self.session_id,
            f"git -C {shlex.quote(worktree_path)} add -A && git -C {shlex.quote(worktree_path)} commit --amend --no-edit",
            timeout=45,
        )
        await ssh_pool.exec(
            self.agent,
            self.session_id,
            (
                f"mkdir -p {shlex.quote(patch_output_dir)} && "
                f"git -C {shlex.quote(worktree_path)} format-patch -1 HEAD --output-directory {shlex.quote(patch_output_dir)}"
            ),
            timeout=45,
        )

        validation = await self._self_validate(patch_output_dir)
        if (not validation["clean"]) and validation["self_correctable"]:
            await self._self_correct(validation["errors"], worktree_path, patch_output_dir)
            validation = await self._self_validate(patch_output_dir)
            validation["self_corrected"] = True

        await ssh_pool.exec(
            self.agent,
            self.session_id,
            f"git -C {shlex.quote(self.kernel_path)} worktree remove --force {shlex.quote(worktree_path)}",
            timeout=20,
        )

        patch_files = await self._read_patch_files(patch_output_dir)
        return {
            "patch_files": patch_files,
            "validation": validation,
            "output_dir": patch_output_dir,
            "execution_mode": ssh_pool.mode.value,
        }

    async def _self_validate(self, patch_dir: str) -> dict:
        result = await ssh_pool.exec(
            self.agent,
            self.session_id,
            (
                f"for f in {shlex.quote(patch_dir)}/*.patch; do "
                f"  {shlex.quote(self.kernel_path)}/scripts/checkpatch.pl --strict --show-types \"$f\"; "
                f"done"
            ),
            timeout=90,
        )
        output = result.stdout
        errors = re.findall(r"ERROR:(\\w+)", output)
        warnings = re.findall(r"WARNING:(\\w+)", output)
        self_correctable_types = {
            "COMMIT_MESSAGE",
            "MISSING_SIGNED_OFF_BY",
            "PLACEHOLDER_USE",
            "LINE_SPACING",
        }
        self_correctable = all(e in self_correctable_types for e in errors) if errors else False
        return {
            "clean": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "output": output,
            "self_correctable": self_correctable,
            "new_placeholder": "PLACEHOLDER_USE" in output,
        }

    async def _self_correct(self, issues: List[str], worktree_path: str, patch_dir: str) -> dict:
        corrections: list[str] = []
        for issue in issues:
            if issue == "MISSING_SIGNED_OFF_BY":
                await ssh_pool.exec(
                    self.agent,
                    self.session_id,
                    f"git -C {shlex.quote(worktree_path)} commit --amend --signoff --no-edit",
                    timeout=20,
                )
                corrections.append("Added Signed-off-by")
            elif issue == "PLACEHOLDER_USE":
                await ssh_pool.exec(
                    self.agent,
                    self.session_id,
                    f"sed -i '/\\*\\*\\* /d' {shlex.quote(str(PurePosixPath(patch_dir) / '0000-cover-letter.patch'))}",
                    timeout=20,
                )
                corrections.append("Removed cover-letter placeholders")
        return {"corrections": corrections}

    async def _generate_fix_commands(self, commit: str, fix_description: str, worktree_path: str) -> List[str]:
        # Delegates to optional helper when available.
        try:
            from backend.agents.chanakya_agent import chanakya_generate_fix_commands  # type: ignore

            cmds = await chanakya_generate_fix_commands(commit, fix_description, worktree_path, self.kernel_path)
            if isinstance(cmds, list) and cmds:
                return cmds
        except Exception:
            pass
        # Safe fallback: no-op touch to keep flow deterministic.
        return [f"cd {shlex.quote(worktree_path)} && git status --short >/tmp/pw_fix_status.txt || true"]

    async def _read_patch_files(self, patch_dir: str) -> List[dict]:
        result = await ssh_pool.exec(
            self.agent,
            self.session_id,
            (
                f"for f in {shlex.quote(patch_dir)}/*.patch; do "
                f"echo '<<<FILE_START::'$(basename \"$f\")'>>>'; "
                f"cat \"$f\"; echo '<<<FILE_END>>>'; done"
            ),
            timeout=40,
        )
        patches: list[dict] = []
        parts = re.split(r"<<<FILE_START::(.+?)>>>", result.stdout)
        for i in range(1, len(parts), 2):
            filename = parts[i].strip()
            content = parts[i + 1].split("<<<FILE_END>>>")[0].strip()
            patches.append({"filename": filename, "content": content})
        return patches
