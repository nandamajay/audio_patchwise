from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def check_for_deadlock(issue_id, session_id, negotiation_state):
    '''
    FIXED: Deadlock only when BOTH conditions true:
    1. CHANAKYA explicitly upheld after receiving challenge
    2. ARYABHATA explicitly challenged with evidence
    Previous bug: timeout alone was triggering deadlock
    '''
    s = negotiation_state.get(issue_id, {})
    upheld = s.get('chanakya_response') == 'UPHELD'
    challenged = s.get('aryabhata_challenged') is True
    has_evidence = bool(s.get('challenge_evidence','').strip())
    timeout_only = s.get('timed_out') is True and not challenged
    if timeout_only:
        logger.info(f'Issue {issue_id}: timeout - auto-proceeding, not deadlock')
        return False
    return upheld and challenged and has_evidence
