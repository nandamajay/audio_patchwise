from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from database import get_db
from websocket_manager import ws_manager


class RebaseStrategy(str, Enum):
    AUTO_REBASE = "auto_rebase"
    SOFT_PAUSE = "soft_pause"
    FREEZE = "freeze_alert"


@dataclass
class UpstreamDrift:
    base_commit: str
    current_head: str
    commits_ahead: int
    affected_files: list[str]
    patch_files: list[str]
    has_conflict: bool


class RebaseHandler:
    def __init__(self):
        self.kernel_repo_path = "/workspace/kernel_src"
        self.check_interval = 1800

    async def monitor_session(
        self,
        session_id: str,
        base_commit: str,
        patch_files: list[str],
        strategy: RebaseStrategy,
    ):
        """Background drift monitor for active review session."""
        while True:
            await asyncio.sleep(self.check_interval)
            drift = await self.detect_drift(base_commit, patch_files)
            if drift and drift.affected_files:
                await self._handle_drift(session_id, drift, strategy)

    async def detect_drift(self, base_commit: str, patch_files: list[str]) -> Optional[UpstreamDrift]:
        """Detect if upstream moved since review started."""
        try:
            subprocess.run(
                ["git", "fetch", "origin", "master"],
                cwd=self.kernel_repo_path,
                capture_output=True,
                check=False,
            )

            result = subprocess.run(
                ["git", "rev-parse", "origin/master"],
                cwd=self.kernel_repo_path,
                capture_output=True,
                text=True,
                check=False,
            )
            current_head = result.stdout.strip()
            if current_head == base_commit:
                return None

            diff_result = subprocess.run(
                ["git", "diff", "--name-only", base_commit, current_head],
                cwd=self.kernel_repo_path,
                capture_output=True,
                text=True,
                check=False,
            )
            changed_files = [line for line in diff_result.stdout.strip().split("\n") if line]
            if patch_files:
                affected_files = [
                    file_path
                    for file_path in changed_files
                    if any(patch_file in file_path for patch_file in patch_files)
                ]
            else:
                affected_files = changed_files

            log_result = subprocess.run(
                ["git", "log", "--oneline", f"{base_commit}..{current_head}"],
                cwd=self.kernel_repo_path,
                capture_output=True,
                text=True,
                check=False,
            )
            commits = [line for line in log_result.stdout.strip().split("\n") if line]
            commits_ahead = len(commits)

            has_conflict = await self._check_conflict(base_commit, patch_files)

            return UpstreamDrift(
                base_commit=base_commit,
                current_head=current_head,
                commits_ahead=commits_ahead,
                affected_files=affected_files,
                patch_files=patch_files,
                has_conflict=has_conflict,
            )
        except Exception as exc:
            print(f"[RebaseHandler] drift detection error: {exc}")
            return None

    async def _check_conflict(self, base_commit: str, patch_files: list[str]) -> bool:
        """Check if patch files likely conflict with upstream changes."""
        del patch_files
        try:
            result = subprocess.run(
                ["git", "merge-tree", base_commit, "HEAD", "origin/master"],
                cwd=self.kernel_repo_path,
                capture_output=True,
                text=True,
                check=False,
            )
            return "<<<<<<" in result.stdout
        except Exception:
            return False

    async def _handle_drift(
        self,
        session_id: str,
        drift: UpstreamDrift,
        strategy: RebaseStrategy,
    ):
        """Handle detected upstream drift based on strategy."""
        db = next(get_db())
        if strategy == RebaseStrategy.AUTO_REBASE:
            await self._auto_rebase(session_id, drift)
        elif strategy == RebaseStrategy.SOFT_PAUSE:
            await ws_manager.emit_to_session(
                session_id,
                "drift_detected",
                {
                    "type": "soft_pause",
                    "commits_ahead": drift.commits_ahead,
                    "affected_files": drift.affected_files,
                    "has_conflict": drift.has_conflict,
                    "message": (
                        f"Upstream moved {drift.commits_ahead} commits ahead. "
                        f"{len(drift.affected_files)} files overlap with your patch."
                    ),
                    "actions": ["auto_rebase", "freeze", "ignore"],
                },
            )
        elif strategy == RebaseStrategy.FREEZE:
            db.execute("UPDATE sessions SET status='frozen_drift' WHERE id=?", (session_id,))
            db.commit()
            await ws_manager.emit_to_session(
                session_id,
                "drift_detected",
                {
                    "type": "freeze",
                    "message": (
                        "Session frozen - upstream drift detected. "
                        "Please rebase manually and resume."
                    ),
                },
            )

    async def _auto_rebase(self, session_id: str, drift: UpstreamDrift):
        """Attempt to auto-rebase patch on latest upstream head."""
        await ws_manager.emit_to_session(
            session_id,
            "rebase_started",
            {
                "message": (
                    "ARYABHATA is rebasing patch onto new upstream HEAD "
                    f"({drift.current_head[:8]})..."
                )
            },
        )

        result = subprocess.run(
            ["git", "rebase", drift.current_head],
            cwd=self.kernel_repo_path,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode == 0:
            await ws_manager.emit_to_session(
                session_id,
                "rebase_complete",
                {
                    "message": (
                        "Rebase successful - patch now applies cleanly on "
                        f"{drift.current_head[:8]}"
                    ),
                    "new_base": drift.current_head,
                    "note": "CHANAKYA will re-check affected context only",
                },
            )
        else:
            await ws_manager.emit_to_session(
                session_id,
                "rebase_conflict",
                {
                    "message": "Rebase has conflicts - manual intervention required",
                    "output": result.stderr,
                },
            )


rebase_handler = RebaseHandler()
