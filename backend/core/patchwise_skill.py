"""
PatchWise Skill — Official Qualcomm PatchWise CLI integration for CHANAKYA.

Official usage:
  patchwise --reviews checkpatch ai_code_review \
            --provider https://qgenie-chat.qualcomm.com/v1
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    from app.security.runtime_secrets import get_runtime_api_key
except Exception:  # pragma: no cover
    def get_runtime_api_key(provider: str) -> str:  # type: ignore[no-redef]
        _ = provider
        return ""


@dataclass
class PatchWiseResult:
    """Structured result from PatchWise skill execution."""

    success: bool
    raw_output: str
    issues: list = field(default_factory=list)
    checkpatch_issues: list = field(default_factory=list)
    ai_review_issues: list = field(default_factory=list)
    lkml_references: list = field(default_factory=list)
    error: Optional[str] = None


class PatchWiseSkill:
    """Wrap the official PatchWise CLI tool for CHANAKYA."""

    def __init__(self):
        self.provider = os.getenv("PATCHWISE_PROVIDER", "https://qgenie-chat.qualcomm.com/v1")
        self.api_key = self._resolve_api_key()
        reviews = os.getenv("PATCHWISE_REVIEWS", "checkpatch,ai_code_review")
        self.reviews = [item.strip() for item in reviews.split(",") if item.strip()]
        if not self.reviews:
            self.reviews = ["checkpatch", "ai_code_review"]
        self._patchwise_help = self._check_installation()
        self._supports_patch_flag = "--patch" in self._patchwise_help
        self._supports_repo_path_flag = "--repo-path" in self._patchwise_help
        self._supports_kernel_flag = "--kernel" in self._patchwise_help
        self.reviews = self._normalize_reviews(self.reviews)

    @staticmethod
    def _is_placeholder(value: str) -> bool:
        normalized = (value or "").strip().lower()
        return normalized in {
            "",
            "your-qgenie-api-key-here",
            "your-openai-key-here",
            "your-anthropic-key-here",
            "your_api_key_here",
        }

    def _resolve_api_key(self) -> str:
        runtime_key = (get_runtime_api_key("qgenie") or "").strip()
        if not self._is_placeholder(runtime_key):
            return runtime_key
        env_key = (os.getenv("QGENIE_API_KEY") or "").strip()
        if not self._is_placeholder(env_key):
            return env_key
        return ""

    @staticmethod
    def _normalize_reviews(reviews: list[str]) -> list[str]:
        mapping = {
            "checkpatch": "Checkpatch",
            "aicodereview": "AiCodeReview",
            "ai_code_review": "AiCodeReview",
            "ai-review": "AiCodeReview",
            "coccicheck": "Coccicheck",
            "dtcheck": "DtCheck",
            "dtbscheck": "DtbsCheck",
            "llmcommitaudit": "LLMCommitAudit",
            "llm_commit_audit": "LLMCommitAudit",
            "sparse": "Sparse",
        }
        normalized: list[str] = []
        for review in reviews:
            key = review.strip().replace("-", "_").replace(" ", "").lower().replace("_", "")
            canonical = mapping.get(key, review.strip())
            if canonical and canonical not in normalized:
                normalized.append(canonical)
        return normalized

    def _check_installation(self) -> str:
        """Verify patchwise is installed and callable."""
        try:
            result = subprocess.run(
                ["patchwise", "--help"],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "PatchWise is not installed. Run: pip install patchwise"
            ) from exc

        if result.returncode != 0:
            raise RuntimeError(
                f"PatchWise is installed but unavailable: {(result.stderr or result.stdout).strip()}"
            )
        return (result.stdout or "") + "\n" + (result.stderr or "")

    @staticmethod
    def _extract_commit_hashes(patch_content: str) -> list[str]:
        seen: set[str] = set()
        hashes: list[str] = []
        for line in patch_content.splitlines():
            match = re.match(r"^From\s+([0-9a-fA-F]{7,40})\s+", line.strip())
            if not match:
                continue
            commit_hash = match.group(1).lower()
            if commit_hash in seen:
                continue
            seen.add(commit_hash)
            hashes.append(commit_hash)
        return hashes

    def review_patch_file(
        self,
        patch_content: str,
        kernel_path: Optional[str] = None,
        subsystem: str = "sound/soc",
        additional_reviews: Optional[list] = None,
    ) -> PatchWiseResult:
        """Run PatchWise review on a patch string."""
        del subsystem

        with tempfile.NamedTemporaryFile(suffix=".patch", mode="w", delete=False) as file_obj:
            file_obj.write(patch_content)
            patch_file = file_obj.name

        try:
            return self._run_patchwise(patch_content, patch_file, kernel_path, additional_reviews)
        finally:
            Path(patch_file).unlink(missing_ok=True)

    def review_commit(
        self,
        commit_hash: str,
        kernel_path: str,
        subsystem: str = "sound/soc",
    ) -> PatchWiseResult:
        """Run PatchWise on a specific git commit."""
        del subsystem
        return self._run_patchwise_commit(commit_hash, kernel_path)

    def _run_patchwise(
        self,
        patch_content: str,
        patch_file: str,
        kernel_path: Optional[str],
        additional_reviews: Optional[list],
    ) -> PatchWiseResult:
        reviews = self.reviews.copy()
        if additional_reviews:
            reviews.extend(self._normalize_reviews([str(item) for item in additional_reviews]))
        reviews = self._normalize_reviews(reviews)

        if self._supports_patch_flag:
            cmd = [
                "patchwise",
                "--reviews",
                *reviews,
                "--provider",
                self.provider,
                "--patch",
                patch_file,
            ]
            if kernel_path and self._supports_kernel_flag:
                cmd.extend(["--kernel", kernel_path])
        else:
            if not kernel_path:
                return PatchWiseResult(
                    success=False,
                    raw_output="",
                    error=(
                        "Installed patchwise CLI supports commit/repo mode only. "
                        "Set source_path to a local kernel repo and submit patches with commit hashes."
                    ),
                )
            commit_hashes = self._extract_commit_hashes(patch_content)
            if not commit_hashes:
                return PatchWiseResult(
                    success=False,
                    raw_output="",
                    error=(
                        "Could not infer commit hashes from patch content for commit-mode patchwise CLI."
                    ),
                )
            cmd = [
                "patchwise",
                "--reviews",
                *reviews,
                "--provider",
                self.provider,
                "--commits",
                *commit_hashes,
            ]
            if self._supports_repo_path_flag:
                cmd.extend(["--repo-path", kernel_path])

        env = os.environ.copy()
        if self.api_key:
            env["OPENAI_API_KEY"] = self.api_key
        env["OPENAI_BASE_URL"] = self.provider

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            timeout=300,
            check=False,
            cwd=kernel_path if (kernel_path and not self._supports_patch_flag) else None,
        )

        return self._parse_output(result.stdout, result.stderr, result.returncode)

    def _run_patchwise_commit(
        self,
        commit_hash: str,
        kernel_path: str,
    ) -> PatchWiseResult:
        env = os.environ.copy()
        if self.api_key:
            env["OPENAI_API_KEY"] = self.api_key
        env["OPENAI_BASE_URL"] = self.provider

        reviews = self._normalize_reviews(self.reviews)
        cmd = [
            "patchwise",
            "--reviews",
            *reviews,
            "--provider",
            self.provider,
            "--commits",
            commit_hash,
        ]
        if self._supports_repo_path_flag:
            cmd.extend(["--repo-path", kernel_path])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            cwd=kernel_path,
            timeout=300,
            check=False,
        )

        return self._parse_output(result.stdout, result.stderr, result.returncode)

    def _parse_output(self, stdout: str, stderr: str, returncode: int) -> PatchWiseResult:
        """Parse PatchWise output into structured issue objects."""
        raw_output = stdout or stderr
        if returncode != 0:
            return PatchWiseResult(
                success=False,
                raw_output=raw_output,
                error=f"PatchWise failed (exit {returncode}): {(stderr or stdout)[:500]}",
            )

        checkpatch_issues = []
        ai_review_issues = []
        lkml_refs = []

        checkpatch_pattern = re.compile(
            r"(ERROR|WARNING|CHECK):\s*(.+?)\s*#(\d+):\s*FILE:\s*(.+?):(\d+)",
            re.MULTILINE,
        )
        for match in checkpatch_pattern.finditer(stdout):
            severity, msg, _, file_path, line = match.groups()
            checkpatch_issues.append(
                {
                    "type": "STYLE",
                    "severity": severity,
                    "message": msg.strip(),
                    "file": file_path.strip(),
                    "line_number": int(line),
                    "source": "checkpatch",
                }
            )

        json_pattern = re.compile(r"```json\s*({.+?})\s*```", re.DOTALL)
        for match in json_pattern.finditer(stdout):
            try:
                data = json.loads(match.group(1))
                if isinstance(data.get("issues"), list):
                    ai_review_issues.extend(data["issues"])
                if isinstance(data.get("lkml_references"), list):
                    lkml_refs.extend(data["lkml_references"])
            except json.JSONDecodeError:
                continue

        issues = checkpatch_issues + ai_review_issues
        return PatchWiseResult(
            success=True,
            raw_output=stdout,
            issues=issues,
            checkpatch_issues=checkpatch_issues,
            ai_review_issues=ai_review_issues,
            lkml_references=lkml_refs,
        )

    def get_status(self) -> dict:
        """Health check payload for System Health dashboard."""
        try:
            result = subprocess.run(
                ["patchwise", "--help"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            return {
                "installed": result.returncode == 0,
                "version": "patchwise-cli",
                "provider": self.provider,
                "reviews": self.reviews,
                "supports_patch_flag": self._supports_patch_flag,
                "supports_repo_path_flag": self._supports_repo_path_flag,
                "api_key_set": bool(self.api_key),
            }
        except Exception as exc:  # pragma: no cover
            return {"installed": False, "error": str(exc)}

    async def _ensure_source_files(self, patch_content, kernel_version):
        try:
            import aiohttp
        except Exception:
            aiohttp = None
            import httpx

        file_paths = re.findall(r'diff --git a/(\S+) b/', patch_content)
        missing, fetched = [], []
        for fp in file_paths:
            local = Path(f'/workspace/kernel_source/{fp}')
            if local.exists():
                continue
            try:
                url = (
                    f'https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git'
                    f'/plain/{fp}?h=v{kernel_version}'
                )
                if aiohttp is not None:
                    async with aiohttp.ClientSession() as s:
                        async with s.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                            if resp.status == 200:
                                local.parent.mkdir(parents=True, exist_ok=True)
                                local.write_text(await resp.text())
                                fetched.append(fp)
                            else:
                                missing.append(fp)
                else:
                    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                        resp = await client.get(url)
                        if resp.status_code == 200:
                            local.parent.mkdir(parents=True, exist_ok=True)
                            local.write_text(resp.text)
                            fetched.append(fp)
                        else:
                            missing.append(fp)
            except Exception:
                missing.append(fp)
        return {'fetched': fetched, 'missing': missing, 'all_available': len(missing) == 0}

    async def run_with_fallback(self, patch_content, kernel_version):
        status = await self._ensure_source_files(patch_content, kernel_version)
        if not status['all_available'] and status['missing']:
            missing_list = chr(10).join([f'- {f}' for f in status['missing'][:5]])
            return {
                'status': 'NEEDS_SOURCE',
                'message': (
                    f'Kernel source files needed for full analysis:{chr(10)}{missing_list}{chr(10)}{chr(10)}'
                    f'Please provide your local kernel source path in the Context section,{chr(10)}'
                    f'or proceeding with QGenie AI review (reduced accuracy).'
                ),
                'fallback': True,
                'missing_files': status['missing'],
            }
        return await self._run_full_patchwise(patch_content, kernel_version)

    async def _run_full_patchwise(self, patch_content, kernel_version=None):
        del kernel_version
        return self.review_patch_file(patch_content=patch_content)
