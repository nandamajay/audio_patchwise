import json, re, asyncio
from typing import Dict, Any, List
from .fix_engine import AryabhataFixEngine
from .prompts import ARYABHATA_SYSTEM_PROMPT, ARYABHATA_FIX_INSTRUCTION
from ..shared.llm_factory import LLMFactory
from ..shared.websocket_manager import stream_agent_message
import logging
logger = logging.getLogger(__name__)

MARKER_START = '<<<FIXED_PATCH_START>>>'
MARKER_END = '<<<FIXED_PATCH_END>>>'

async def aryabhata_node(state: Dict[str, Any]) -> Dict[str, Any]:
    session_id = state['session_id']
    issues = state.get('current_issues', [])
    patch_content = state.get('patch_content', '')
    subsystem = state.get('subsystem', 'ASoC')
    kernel_version = state.get('kernel_version', '6.8')

    await stream_agent_message(session_id, 'aryabhata', 'thinking',
        f'Analyzing {len(issues)} issues from CHANAKYA. Preparing to apply fixes...')

    # Split into deterministic vs LLM-required
    deterministic, llm_issues = [], []
    for issue in issues:
        is_cover = ('cover' in issue.get('description','').lower() or
                    'cover-letter' in issue.get('filename','').lower())
        has_code = bool(issue.get('problematic_code','').strip())
        has_fix = bool(issue.get('suggested_fix','').strip())
        (llm_issues if is_cover or not (has_code and has_fix) else deterministic).append(issue)

    # Apply deterministic fixes
    engine = AryabhataFixEngine(subsystem=subsystem, kernel_version=kernel_version)
    engine_result = None
    if deterministic:
        await stream_agent_message(session_id, 'aryabhata', 'thinking',
            f'Applying {len(deterministic)} direct line-level fixes...')
        engine_result = engine.apply_all_fixes(patch_content=patch_content, issues=deterministic)
        if engine_result.success:
            patch_content = engine_result.fixed_patch_content
            await stream_agent_message(session_id, 'aryabhata', 'thinking',
                f'[OK] Fixed lines: {engine_result.changed_lines}')
        else:
            llm_issues.extend(deterministic)

    # LLM-assisted fixes
    llm_fixed = patch_content
    cover_letter = None
    if llm_issues:
        await stream_agent_message(session_id, 'aryabhata', 'thinking',
            f'Using QGenie LLM for {len(llm_issues)} complex/cover letter fixes...')
        llm = LLMFactory.create()
        prompt = ARYABHATA_FIX_INSTRUCTION.format(
            issues_json=json.dumps(llm_issues, indent=2),
            patch_content=patch_content[:8000],
            kernel_version=kernel_version, subsystem=subsystem,
            patch_version=state.get('patch_version',''),
            prev_version_links=json.dumps(state.get('previous_version_links',[])))
        messages = [{'role':'system','content':ARYABHATA_SYSTEM_PROMPT},
                    {'role':'user','content':prompt}]
        full_response = ''
        async for chunk in llm.astream(messages):
            text = getattr(chunk, 'content', str(chunk))
            full_response += text
            await stream_agent_message(session_id, 'aryabhata', 'stream', text)
        blocks = re.findall(rf'{re.escape(MARKER_START)}(.*?){re.escape(MARKER_END)}',
                            full_response, re.DOTALL)
        if blocks:
            for b in blocks:
                b = b.strip()
                if '0/2' in b or '0/1' in b or 'cover-letter' in b.lower(): cover_letter = b
                else: llm_fixed = b
        else:
            logger.error('ARYABHATA LLM did not produce FIXED_PATCH markers')
            await stream_agent_message(session_id, 'aryabhata', 'warning',
                'LLM did not produce patch markers - using engine fixes')

    final = llm_fixed or patch_content
    changed = sorted(set(engine_result.changed_lines if engine_result else []))

    await stream_agent_message(session_id, 'aryabhata', 'fix_complete', {
        'fixed_patch': final, 'cover_letter': cover_letter, 'changed_lines': changed,
        'surgical_review_request': {'lines': changed,
            'message': f'CHANAKYA: please re-check lines {changed} only'}})

    return {**state, 'patch_content': final, 'cover_letter_content': cover_letter,
            'aryabhata_changed_lines': changed, 'aryabhata_fix_complete': True,
            'surgical_review_lines': changed, 'fix_round': state['current_round']}
