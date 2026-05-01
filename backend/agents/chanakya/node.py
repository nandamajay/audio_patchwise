from __future__ import annotations

from typing import Any, Dict

from .version_intelligence import PatchVersionIntelligence
from ..shared.websocket_manager import stream_agent_message


async def pre_review_analysis(state: Dict[str, Any]) -> Dict[str, Any]:
    session_id = state['session_id']
    patch_content = state.get('patch_content', '')
    user_link = state.get('lore_link') or state.get('gerrit_link') or ''

    await stream_agent_message(session_id, 'chanakya', 'thinking',
        'Analyzing with PatchWise (checkpatch + ai_code_review) and QGenie deep review. '
        'Detecting patch version and prior review history...')

    vi = PatchVersionIntelligence()
    chain = await vi.get_version_chain(
        patch_content=patch_content, user_provided_link=user_link, session_id=session_id)

    if chain.fetch_status == 'NO_HISTORY':
        await stream_agent_message(session_id, 'chanakya', 'info',
            'v1 patch detected - no prior version history. Reviewing standalone.')

    elif chain.fetch_status == 'DEGRADED':
        if chain.found_via == 'not_found':
            await stream_agent_message(session_id, 'chanakya', 'needs_input', {
                'message': (f'This appears to be v{chain.current_version} but no previous '
                            f'version link was found. Searched by subject - not found. '
                            f'Please provide the lore.kernel.org link to v{chain.current_version-1} '
                            f'for complete context. Proceeding with standalone review.'),
                'type': 'version_link_needed',
                'version': chain.current_version - 1})
        else:
            await stream_agent_message(session_id, 'chanakya', 'warning',
                f'lore.kernel.org temporarily unreachable. '
                f'Reviewing v{chain.current_version} standalone (reduced context).')

    elif chain.fetch_status == 'SUCCESS':
        await stream_agent_message(session_id, 'chanakya', 'version_history', {
            'message': (f'Version history loaded: {len(chain.versions)} previous version(s)\n'
                       f'{len(chain.reviewer_comments)} reviewer comments found\n'
                       f'{len(chain.addressed_comments)} addressed in this version\n'
                       f'{len(chain.unaddressed_comments)} unaddressed - require attention'),
            'unaddressed': [{'author': c.author, 'role': c.role,
                             'preview': c.body[:100], 'suggested_reply': c.suggested_reply,
                             'reply_quality': c.reply_quality}
                            for c in chain.unaddressed_comments]})

    return {**state, 'version_chain': chain, 'version_intelligence_complete': True}
