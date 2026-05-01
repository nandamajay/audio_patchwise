from __future__ import annotations

from typing import Any, Dict

from api.dependencies import session_manager


BROADCAST_EVENTS = {
    'round_started', 'chanakya_review_complete', 'aryabhata_fix_complete',
    'lgtm', 'max_rounds_reached', 'deadlock_detected', 'soft_interrupt'
}


async def on_state_change(state: Dict[str, Any], event: str):
    if event in BROADCAST_EVENTS:
        await session_manager.broadcast_session_update(
            session_id=state.get('session_id',''),
            event_type=event,
            data={'round': state.get('current_round',0),
                  'status': state.get('session_status','RUNNING'),
                  'patch_quality': state.get('patch_quality_score',0)}
        )
    # All other state changes -> SILENT (prevents sidebar spam)
