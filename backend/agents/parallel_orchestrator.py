from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from agents.aryabhata_executor import AryabhataExecutor
from agents.chanakya_executor import ChanakyaExecutor
from graph.state import fix_ready_event

logger = logging.getLogger("uvicorn.error")


class SmartParallelOrchestrator:
    """
    CHANAKYA review+fix and ARYABHATA preload run in parallel.
    Total time ~= max(chanakya, preload) + validation.
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.chanakya = ChanakyaExecutor(session_id)
        self.aryabhata = AryabhataExecutor(session_id)

    async def run_parallel_review(self, commits: list[str], patch_dir: str, issues: list[dict] | None = None) -> dict[str, Any]:
        issues = issues or []
        fix_ready_event.clear()

        chanakya_task = asyncio.create_task(self._chanakya_pipeline(commits, patch_dir))
        aryabhata_preload_task = asyncio.create_task(self.aryabhata.preload_context(commits, patch_files=[]))

        # Both start at t=0 (smart_parallel preload while fix is running)
        chanakya_result = await chanakya_task
        fix_ready_event.set()
        logger.info("[Parallel] CHANAKYA fix_ready signal sent")

        await aryabhata_preload_task
        aryabhata_result = await self.aryabhata.validate_chanakya_fix(
            fixed_patches=chanakya_result.get("patch_files", []),
            original_issues=issues,
            commits=commits,
        )
        return {
            "chanakya": chanakya_result,
            "aryabhata": aryabhata_result,
            "verdict": aryabhata_result.get("verdict", "NEEDS_WORK"),
            "parallel_saved": True,
        }

    async def _chanakya_pipeline(self, commits: list[str], patch_dir: str) -> dict[str, Any]:
        await self.chanakya.explore_patch_dir(patch_dir)
        patchwise = await self.chanakya.run_patchwise(commits)
        git_show = await self.chanakya.run_git_show(commits)
        patch_output_dir = os.path.join(patch_dir, "fixed")
        fixed = await self.chanakya.apply_fix_and_format_patch(
            commit=commits[0] if commits else "HEAD",
            fix_description="Auto-fix issues detected during review",
            patch_output_dir=patch_output_dir,
        )
        return {
            "patchwise": patchwise,
            "git_show": git_show,
            **fixed,
        }
