from __future__ import annotations

import asyncio
import shlex
from dataclasses import dataclass
from enum import Enum
from typing import Any


class CheckStatus(Enum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    PENDING = "pending"


@dataclass
class PreflightCheck:
    name: str
    description: str
    status: CheckStatus
    message: str
    command_run: str = ""


class DryRunManager:
    """
    Validates Gerrit/GitHub credentials and patch format before submission.
    Exposes default command generation so users can edit before execution.
    """

    async def run_gerrit_preflight(self, config: dict[str, Any]) -> list[PreflightCheck]:
        checks: list[PreflightCheck] = []

        ssh_cmd = (
            f"ssh -p {config.get('gerrit_port', 29418)} "
            f"{config.get('gerrit_user', '')}@{config.get('gerrit_host', '')} gerrit version"
        )
        result = await self._run_command(ssh_cmd)
        checks.append(
            PreflightCheck(
                name="Gerrit SSH Auth",
                description="Validates SSH key authentication to Gerrit server",
                status=CheckStatus.PASS if result["returncode"] == 0 else CheckStatus.FAIL,
                message=result["stdout"] if result["returncode"] == 0 else f"Auth failed: {result['stderr']}",
                command_run=ssh_cmd,
            )
        )

        if result["returncode"] == 0:
            ls_cmd = (
                f"ssh -p {config.get('gerrit_port', 29418)} "
                f"{config.get('gerrit_user', '')}@{config.get('gerrit_host', '')} "
                "gerrit ls-projects --format JSON"
            )
            ls_result = await self._run_command(ls_cmd)
            project_accessible = config.get("gerrit_project", "") in ls_result.get("stdout", "")
            checks.append(
                PreflightCheck(
                    name="Gerrit Repo Access",
                    description=f"Checks access to project: {config.get('gerrit_project')}",
                    status=CheckStatus.PASS if project_accessible else CheckStatus.WARN,
                    message="Project accessible" if project_accessible else "Project not found in accessible list",
                    command_run=ls_cmd,
                )
            )

        patch_check_cmd = f"git apply --check {shlex.quote(config.get('patch_path', ''))}"
        patch_result = await self._run_command(patch_check_cmd, cwd=config.get("repo_path", "."))
        checks.append(
            PreflightCheck(
                name="Patch Format Validation",
                description="Verifies patch applies cleanly with git apply --check",
                status=CheckStatus.PASS if patch_result["returncode"] == 0 else CheckStatus.FAIL,
                message="Patch applies cleanly" if patch_result["returncode"] == 0 else patch_result["stderr"],
                command_run=patch_check_cmd,
            )
        )

        push_cmd = (
            f"git push --dry-run {shlex.quote(config.get('gerrit_remote', 'gerrit'))} "
            f"HEAD:refs/for/{shlex.quote(config.get('target_branch', 'main'))}"
        )
        push_result = await self._run_command(push_cmd, cwd=config.get("repo_path", "."))
        checks.append(
            PreflightCheck(
                name="Gerrit Push Dry Run",
                description="Simulates git push to Gerrit without actually pushing",
                status=CheckStatus.PASS if push_result["returncode"] == 0 else CheckStatus.WARN,
                message=push_result["stdout"] or push_result["stderr"],
                command_run=push_cmd,
            )
        )

        return checks

    async def run_github_preflight(self, config: dict[str, Any]) -> list[PreflightCheck]:
        checks: list[PreflightCheck] = []

        token_cmd = "gh auth status"
        result = await self._run_command(token_cmd, env={"GH_TOKEN": config.get("github_token", "")})
        checks.append(
            PreflightCheck(
                name="GitHub Token Auth",
                description="Validates GitHub CLI authentication",
                status=CheckStatus.PASS if result["returncode"] == 0 else CheckStatus.FAIL,
                message="Authenticated" if result["returncode"] == 0 else f"Auth failed: {result['stderr']}",
                command_run=token_cmd,
            )
        )

        repo_cmd = f"gh repo view {shlex.quote(config.get('github_repo', ''))}"
        repo_result = await self._run_command(repo_cmd)
        checks.append(
            PreflightCheck(
                name="GitHub Repo Access",
                description=f"Verifies access to {config.get('github_repo')}",
                status=CheckStatus.PASS if repo_result["returncode"] == 0 else CheckStatus.FAIL,
                message="Repo accessible" if repo_result["returncode"] == 0 else repo_result["stderr"],
                command_run=repo_cmd,
            )
        )

        target_branch = config.get("target_branch", "main")
        branch_cmd = f"gh api repos/{config.get('github_repo', '')}/branches/{target_branch}"
        branch_result = await self._run_command(branch_cmd)
        checks.append(
            PreflightCheck(
                name="Target Branch Exists",
                description=f"Confirms target branch {target_branch} exists",
                status=CheckStatus.PASS if branch_result["returncode"] == 0 else CheckStatus.WARN,
                message="Branch exists" if branch_result["returncode"] == 0 else "Branch not found - will be created",
                command_run=branch_cmd,
            )
        )

        patch_cmd = f"git apply --check {shlex.quote(config.get('patch_path', ''))}"
        patch_result = await self._run_command(patch_cmd, cwd=config.get("repo_path", "."))
        checks.append(
            PreflightCheck(
                name="Patch Format Validation",
                description="Verifies patch applies cleanly",
                status=CheckStatus.PASS if patch_result["returncode"] == 0 else CheckStatus.FAIL,
                message="Patch applies cleanly" if patch_result["returncode"] == 0 else patch_result["stderr"],
                command_run=patch_cmd,
            )
        )

        return checks

    async def run_upstream_preflight(self, config: dict[str, Any]) -> list[PreflightCheck]:
        checks: list[PreflightCheck] = []

        smtp_cmd = "which sendmail || which msmtp"
        smtp_result = await self._run_command(smtp_cmd)
        checks.append(
            PreflightCheck(
                name="Email Transport",
                description="Verifies sendmail or msmtp is available for upstream submission",
                status=CheckStatus.PASS if smtp_result["returncode"] == 0 else CheckStatus.FAIL,
                message="Email transport available" if smtp_result["returncode"] == 0 else "No email transport found",
                command_run=smtp_cmd,
            )
        )

        send_cmd = (
            "git send-email --dry-run "
            f"--to={shlex.quote(config.get('maintainer_email', 'alsa-devel@alsa-project.org'))} "
            f"{shlex.quote(config.get('patch_path', ''))}"
        )
        send_result = await self._run_command(send_cmd, cwd=config.get("repo_path", "."))
        checks.append(
            PreflightCheck(
                name="git send-email Dry Run",
                description="Simulates patch email without actually sending",
                status=CheckStatus.PASS if send_result["returncode"] == 0 else CheckStatus.WARN,
                message=(send_result["stdout"] or send_result["stderr"])[:200],
                command_run=send_cmd,
            )
        )

        return checks

    def build_submission_command(self, target: str, config: dict[str, Any]) -> str:
        if target == "gerrit":
            return (
                f"git push {config.get('gerrit_remote', 'gerrit')} "
                f"HEAD:refs/for/{config.get('target_branch', 'main')}"
            )

        if target == "github":
            patch_title = config.get("patch_title", "Patch: fix audio driver issue")
            pr_body = config.get("pr_body", "Auto-generated by PatchWise")
            return (
                "gh pr create "
                f"--repo {config.get('github_repo', 'owner/repo')} "
                f"--base {config.get('target_branch', 'main')} "
                f"--title {shlex.quote(patch_title)} "
                f"--body {shlex.quote(pr_body)}"
            )

        if target == "upstream":
            return (
                "git send-email "
                f"--to={config.get('maintainer_email', 'alsa-devel@alsa-project.org')} "
                f"--cc={config.get('cc_email', 'linux-kernel@vger.kernel.org')} "
                '--subject-prefix="PATCH" '
                f"{config.get('patch_path', 'patches/0001-fix.patch')}"
            )

        return ""

    async def execute_command(self, command: str, cwd: str = ".") -> dict[str, Any]:
        return await self._run_command(command, cwd=cwd)

    async def _run_command(
        self,
        cmd: str,
        cwd: str = ".",
        env: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            import os

            full_env = {**os.environ, **(env or {})}
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=full_env,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            return {
                "returncode": proc.returncode,
                "stdout": stdout.decode().strip(),
                "stderr": stderr.decode().strip(),
            }
        except asyncio.TimeoutError:
            return {"returncode": -1, "stdout": "", "stderr": "Command timed out after 30s"}
        except Exception as exc:  # pragma: no cover - defensive runtime wrapper
            return {"returncode": -1, "stdout": "", "stderr": str(exc)}
