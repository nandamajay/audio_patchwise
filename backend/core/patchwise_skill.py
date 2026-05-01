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
        self._check_installation()

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

    def _check_installation(self):
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
            return self._run_patchwise(patch_file, kernel_path, additional_reviews)
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
        patch_file: str,
        kernel_path: Optional[str],
        additional_reviews: Optional[list],
    ) -> PatchWiseResult:
        reviews = self.reviews.copy()
        if additional_reviews:
            reviews.extend(additional_reviews)

        cmd = [
            "patchwise",
            "--reviews",
            *reviews,
            "--provider",
            self.provider,
            "--patch",
            patch_file,
        ]

        if kernel_path:
            cmd.extend(["--kernel", kernel_path])

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

        result = subprocess.run(
            [
                "patchwise",
                "--reviews",
                *self.reviews,
                "--provider",
                self.provider,
                "--commits",
                commit_hash,
            ],
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
        if returncode != 0 and not stdout:
            return PatchWiseResult(
                success=False,
                raw_output=stderr,
                error=f"PatchWise failed (exit {returncode}): {stderr[:500]}",
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
                "api_key_set": bool(self.api_key),
            }
        except Exception as exc:  # pragma: no cover
            return {"installed": False, "error": str(exc)}
