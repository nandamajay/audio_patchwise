from __future__ import annotations

import os
import subprocess
import tempfile
from enum import Enum

try:
    from github import Github, GithubException
except Exception:  # pragma: no cover
    Github = None

    class GithubException(Exception):
        pass

from session.session_manager import SessionManager


class SubmissionTarget(str, Enum):
    GITHUB = "github"
    GERRIT = "gerrit"
    UPSTREAM = "upstream"
    DOWNLOAD = "download"


class SubmissionStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    FAILED = "failed"


class SubmissionEngine:
    def __init__(self, config: dict, session_manager: SessionManager):
        self.config = config
        self.sm = session_manager

    async def submit_to_github(self, session_id: str, pr_config: dict) -> dict:
        session = self.sm.get_session(session_id)
        if not session:
            return {"status": SubmissionStatus.FAILED, "error": "Session not found"}

        if Github is None:
            return {
                "status": SubmissionStatus.FAILED,
                "error": "PyGithub dependency unavailable",
            }

        try:
            g = Github(self.config.get("GITHUB_TOKEN", ""))
            repo = g.get_repo(pr_config["target_repo"])
            base_sha = repo.get_branch(pr_config.get("base_branch", "main")).commit.sha
            branch_name = f"patchwise/{session_id[:8]}"

            try:
                repo.get_git_ref(f"heads/{branch_name}")
            except Exception:
                repo.create_git_ref(f"refs/heads/{branch_name}", base_sha)

            commit_message = self._extract_commit_message(session.final_patch or "")
            pr_body = self._build_pr_body(session)

            pr = repo.create_pull(
                title=commit_message.split("\n")[0],
                body=pr_body,
                head=branch_name,
                base=pr_config.get("base_branch", "main"),
            )

            return {
                "status": SubmissionStatus.SUBMITTED,
                "url": pr.html_url,
                "pr_number": pr.number,
            }
        except GithubException as error:
            return {"status": SubmissionStatus.FAILED, "error": str(error)}

    async def submit_to_gerrit(self, session_id: str, gerrit_config: dict) -> dict:
        session = self.sm.get_session(session_id)
        if not session:
            return {"status": SubmissionStatus.FAILED, "error": "Session not found"}

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                subprocess.run(["git", "init"], cwd=tmpdir, check=True)
                subprocess.run(
                    ["git", "remote", "add", "origin", gerrit_config["gerrit_url"]],
                    cwd=tmpdir,
                    check=True,
                )
                subprocess.run(["git", "fetch", "origin"], cwd=tmpdir, check=True)
                branch = gerrit_config.get("branch", "main")
                subprocess.run(["git", "checkout", branch], cwd=tmpdir, check=True)

                patch_file = os.path.join(tmpdir, "fix.patch")
                with open(patch_file, "w", encoding="utf-8") as handle:
                    handle.write(session.final_patch or "")

                subprocess.run(["git", "am", patch_file], cwd=tmpdir, check=True)
                result = subprocess.run(
                    ["git", "push", "origin", f"HEAD:refs/for/{branch}"],
                    cwd=tmpdir,
                    capture_output=True,
                    text=True,
                    check=False,
                )

                if result.returncode != 0:
                    return {"status": SubmissionStatus.FAILED, "error": result.stderr}

                gerrit_url = self._extract_gerrit_url(result.stderr)
                return {"status": SubmissionStatus.SUBMITTED, "url": gerrit_url}
        except Exception as error:  # pragma: no cover
            return {"status": SubmissionStatus.FAILED, "error": str(error)}

    async def format_upstream_patch(self, session_id: str) -> dict:
        session = self.sm.get_session(session_id)
        if not session:
            return {"status": SubmissionStatus.FAILED, "error": "Session not found"}

        patch = session.final_patch or ""
        checkpatch_result = self._run_checkpatch(patch)
        cover_letter = self._generate_cover_letter(session)

        if "Signed-off-by:" not in patch:
            patch = self._add_signoff(patch, self.config.get("USER_EMAIL", "patchwise@local"))

        return {
            "status": SubmissionStatus.SUBMITTED,
            "formatted_patch": patch,
            "cover_letter": cover_letter,
            "checkpatch_result": checkpatch_result,
            "email_instructions": {
                "to": "alsa-devel@alsa-project.org",
                "cc": "linux-kernel@vger.kernel.org",
                "subject": self._extract_commit_message(patch).split("\n")[0],
            },
        }

    async def download_patch(self, session_id: str) -> dict:
        session = self.sm.get_session(session_id)
        if not session:
            return {"status": SubmissionStatus.FAILED, "error": "Session not found"}
        return {
            "status": SubmissionStatus.SUBMITTED,
            "filename": f"patchwise-{session_id[:8]}.patch",
            "content": session.final_patch or "",
        }

    def _extract_commit_message(self, patch: str) -> str:
        for line in patch.split("\n"):
            if line.startswith("Subject:"):
                return line.replace("Subject:", "").strip()
        return "Fix: PatchWise automated review"

    def _build_pr_body(self, session) -> str:
        report = session.review_report or {}
        issues = session.issues_found or []
        resolved = len([item for item in issues if isinstance(item, dict) and item.get("resolved")])
        return f"""## 🏛️ PatchWise Automated Review

**Session:** `{session.session_id[:8]}`
**Verdict:** {session.verdict}
**Rounds:** {session.current_round}/{session.max_rounds}
**Issues Found:** {len(issues)}
**Issues Resolved:** {resolved}

---

### CHANAKYA Review Summary
{report.get('summary', 'See conversation log for details')}

---

### ARYABHATA Fix Justification
{report.get('justification', 'See conversation log for details')}

---
*Generated by PatchWise A2A Review System*
"""

    def _run_checkpatch(self, patch: str) -> dict:
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".patch", delete=False) as handle:
                handle.write(patch)
                handle.flush()
                checkpatch = self.config.get("CHECKPATCH_PATH", "checkpatch.pl")
                result = subprocess.run(
                    ["perl", checkpatch, "--no-tree", handle.name],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                return {
                    "output": result.stdout,
                    "errors": result.stderr,
                    "passed": result.returncode == 0,
                }
        except Exception as error:
            return {"output": "", "errors": str(error), "passed": False}

    def _generate_cover_letter(self, session) -> str:
        return f"""From: PatchWise Agent <patchwise@review>
Subject: [PATCH] {self._extract_commit_message(session.final_patch or '')}

This patch was reviewed by PatchWise A2A system.

CHANAKYA (Reviewer) and ARYABHATA (Developer) collaborated over
{session.current_round} rounds to produce this fix.

Signed-off-by: {self.config.get('USER_NAME', 'PatchWise')} <{self.config.get('USER_EMAIL', 'patchwise@local')}>
---
"""

    def _add_signoff(self, patch: str, email: str) -> str:
        return patch + f"\nSigned-off-by: {email}\n"

    def _extract_gerrit_url(self, stderr: str) -> str:
        for line in stderr.split("\n"):
            if "http" in line:
                return line.strip()
        return ""
