from __future__ import annotations

import asyncio
from typing import Optional

from core.message_bus import BusMessage, MessageType


class A2ABehaviors:
    """
    Inject 21 true A2A behavior pack.
    Keeps agent autonomy high and user touchpoints minimal.
    """

    def __init__(self, db, bus, ssh):
        self.db = db
        self.bus = bus
        self.ssh = ssh

    async def chanakya_pre_fix_consultation(self, session_id: str, issue: dict) -> dict:
        await self.bus.publish(
            BusMessage(
                session_id=session_id,
                sender="chanakya",
                recipient="aryabhata",
                message_type=MessageType.PRE_FIX_CONSULTATION,
                content={"issue": issue},
            )
        )
        response = await self.bus.wait_for_response(
            session_id=session_id,
            sender="aryabhata",
            message_type=MessageType.PRE_FIX_RESPONSE,
            timeout=45,
        )
        return response or {"advice": "no_response"}

    async def aryabhata_proactive_risk_flag(self, session_id: str, risk: dict) -> None:
        await self.bus.publish(
            BusMessage(
                session_id=session_id,
                sender="aryabhata",
                recipient="chanakya",
                message_type=MessageType.PROACTIVE_RISK_FLAG,
                content=risk,
            )
        )

    async def share_reasoning_context(self, session_id: str, state: dict) -> None:
        payload = {
            "chanakya_reasoning": {
                "why_flagged": state.get("review_reasoning", {}),
                "lkml_references": state.get("similar_patches", []),
                "checkpatch_raw": state.get("checkpatch_output", ""),
                "lsp_findings": state.get("lsp_analysis", {}),
                "confidence_per_issue": state.get("issue_confidence", {}),
            }
        }
        await self.db.save_shared_context(session_id, payload)

    async def joint_user_clarification(
        self,
        session_id: str,
        chanakya_question: str,
        aryabhata_question: str,
    ) -> Optional[str]:
        are_related = await self._questions_related(chanakya_question, aryabhata_question)
        if not are_related:
            return None

        merged = (
            "Both agents need clarification: "
            f"{chanakya_question} "
            "(CHANAKYA needs this for review context; "
            "ARYABHATA needs this for validation)"
        )

        await self.bus.emit_user_clarification(
            session_id,
            {
                "type": "joint_clarification",
                "from": ["chanakya", "aryabhata"],
                "question": merged,
                "urgency": "medium",
            },
        )
        return await self.bus.wait_for_user_input(session_id, timeout=300)

    async def _questions_related(self, q1: str, q2: str) -> bool:
        words1 = set(q1.lower().split())
        words2 = set(q2.lower().split())
        overlap = len(words1 & words2) / max(len(words1 | words2), 1)
        return overlap > 0.3

    async def aryabhata_approval_token(self, session_id: str, final_patch_hash: str) -> Optional[str]:
        result = await self.ssh.aryabhata_exec(
            session_id,
            f"./scripts/checkpatch.pl --strict /tmp/patchwise/aryabhata/{session_id}/final.patch 2>&1",
        )
        output = (result.stdout or "") + (result.stderr or "")
        errors = output.count("ERROR:")
        warnings = output.count("WARNING:")
        if errors != 0:
            return None

        token = f"ARYABHATA-APPROVED-{session_id[:8]}-{final_patch_hash[:8]}"
        await self.db.save_approval_token(session_id, token)
        await self.bus.emit_approval_granted(
            session_id,
            {
                "token": token,
                "checkpatch_errors": errors,
                "checkpatch_warnings": warnings,
                "approved_by": "aryabhata",
                "timestamp": asyncio.get_event_loop().time(),
            },
        )
        return token

    async def autonomous_cover_letter(self, session_id: str, patches: list, lkml_context: dict) -> str:
        await self.bus.publish(
            BusMessage(
                session_id=session_id,
                sender="chanakya",
                recipient="aryabhata",
                message_type=MessageType.COVER_LETTER_REQUEST,
                content={
                    "patches": patches,
                    "lkml_similar": lkml_context.get("similar_patches", []),
                    "maintainer_preferences": lkml_context.get("maintainer_style", {}),
                    "changelog_from_prev_version": lkml_context.get("prev_version_comments", []),
                    "subsystem": "ALSA/ASoC",
                    "author": "Ajay Kumar Nandam <ajay.nandam@oss.qualcomm.com>",
                },
            )
        )

        draft_response = await self.bus.wait_for_response(
            session_id=session_id,
            sender="aryabhata",
            message_type=MessageType.COVER_LETTER_DRAFT,
            timeout=120,
        )
        draft = (draft_response or {}).get("draft", "")

        if draft:
            await self.bus.publish(
                BusMessage(
                    session_id=session_id,
                    sender="chanakya",
                    recipient="aryabhata",
                    message_type=MessageType.REVIEW_COVER_LETTER,
                    content={"draft": draft},
                )
            )

        await self.bus.emit_cover_letter_draft(
            session_id,
            {"draft": draft, "needs_user_approval": True, "auto_generated": True},
        )
        return draft
