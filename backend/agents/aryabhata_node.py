from __future__ import annotations

import json
import re
from typing import Any

from .aryabhata_prompts import ARYABHATA_SYSTEM_PROMPT, ARYABHATA_FIX_INSTRUCTION

PatchWiseState = dict[str, Any]


async def _stream_token(state: PatchWiseState, token: str) -> None:
    callback = state.get("_stream_callback")
    if callable(callback):
        callback(
            {
                "agent": "aryabhata",
                "type": "thinking",
                "round": state.get("current_round", 1),
                "content": token,
                "metadata": {},
            }
        )


async def aryabhata_apply_fixes(state: PatchWiseState, llm) -> PatchWiseState:
    """
    ARYABHATA applies actual fixes to patch content.

    Enforces marker output and retries if markers are missing.
    """
    review = state.get("current_review") or state.get("latest_review") or {}
    patch_content = state.get("original_patch") or state.get("current_patch") or state.get("patch_input", "")
    version_context = state.get("version_context", "No previous version context.")

    issues_text = format_issues_for_aryabhata(review.get("issues", []))
    instruction = ARYABHATA_FIX_INSTRUCTION.format(
        patch_content=patch_content,
        review_issues=issues_text,
        version_context=version_context,
    )

    messages = [
        {"role": "system", "content": ARYABHATA_SYSTEM_PROMPT},
        {"role": "user", "content": instruction},
    ]

    full_response = ""
    async for chunk in llm.astream(messages):
        token = chunk.content if hasattr(chunk, "content") else str(chunk)
        full_response += token
        await _stream_token(state, token)

    if "<<<FIXED_PATCH_START" not in full_response:
        retry_instruction = f"""
{instruction}

CRITICAL WARNING: Your previous response did NOT contain patch markers.
You MUST output fixed patch content between these markers:
<<<FIXED_PATCH_START:filename>>>
[complete file content]
<<<FIXED_PATCH_END:filename>>>

The patch content to fix is:
{patch_content}

OUTPUT THE FIXED PATCH NOW WITH MARKERS:
"""
        messages_retry = [
            {"role": "system", "content": ARYABHATA_SYSTEM_PROMPT},
            {"role": "user", "content": retry_instruction},
        ]

        full_response = ""
        async for chunk in llm.astream(messages_retry):
            token = chunk.content if hasattr(chunk, "content") else str(chunk)
            full_response += token
            await _stream_token(state, token)

    fixed_patches = parse_fixed_patches(full_response)
    fix_summary = parse_fix_summary(full_response)

    if not fixed_patches:
        fixed_patches = apply_rule_based_fixes(patch_content, review.get("issues", []))
        fix_summary = [f"Rule-based fix applied for {i.get('type', 'UNKNOWN')}" for i in review.get("issues", [])]

    state["fixed_patches"] = fixed_patches
    state["fix_summary"] = fix_summary
    state["aryabhata_response"] = full_response

    return state


def format_issues_for_aryabhata(issues: list[dict[str, Any]]) -> str:
    lines = []
    for i, issue in enumerate(issues, 1):
        lines.append(
            f"""
Issue #{i} [{issue.get('type', issue.get('category', 'STYLE'))}]:
  File: {issue.get('file', issue.get('file_path', 'patch'))}
  Line: {issue.get('line_number', 1)}
  Problematic Code: {issue.get('problematic_code', '')}
  Error: {issue.get('error_description', issue.get('error_message', ''))}
  Required Fix: {issue.get('suggested_fix', '')}
  Reference: {issue.get('reference', 'N/A')}
"""
        )
    return "\n".join(lines)


def parse_fixed_patches(response: str) -> dict[str, str]:
    patches: dict[str, str] = {}
    pattern = r"<<<FIXED_PATCH_START:([^>]+)>>>(.*?)<<<FIXED_PATCH_END:\1>>>"
    matches = re.findall(pattern, response, re.DOTALL)
    for filename, content in matches:
        patches[filename.strip()] = content.strip()
    return patches


def parse_fix_summary(response: str) -> list[str]:
    pattern = r"<<<FIX_SUMMARY_START>>>(.*?)<<<FIX_SUMMARY_END>>>"
    match = re.search(pattern, response, re.DOTALL)
    if match:
        lines = match.group(1).strip().split("\n")
        return [line.strip("- ").strip() for line in lines if line.strip()]
    return []


def apply_rule_based_fixes(patch_content: str, issues: list[dict[str, Any]]) -> dict[str, str]:
    content = patch_content

    for issue in issues:
        issue_type = str(issue.get("type", issue.get("category", ""))).upper()

        if issue_type == "COMMIT":
            if "subsystem prefix" in str(issue.get("error_description", issue.get("error_message", ""))).lower():
                subsystem = extract_subsystem_from_patch(content)
                content = fix_commit_subject(content, subsystem)
            elif "signed-off-by" in str(issue.get("error_description", issue.get("error_message", ""))).lower():
                content = add_signed_off_by(content)

        elif issue_type == "STYLE":
            problematic = str(issue.get("problematic_code", ""))
            suggested = str(issue.get("suggested_fix", ""))
            if problematic and suggested and problematic != suggested:
                content = content.replace(problematic, suggested, 1)

        elif issue_type == "COMPLIANCE":
            err = str(issue.get("error_description", issue.get("error_message", ""))).lower()
            if "changelog" in err:
                content = add_changelog_section(content)
            elif "link:" in err:
                content = add_link_section(content)

    return {"patch": content}


def extract_subsystem_from_patch(content: str) -> str:
    match = re.search(r"diff --git a/(sound/soc/[^/]+)", content)
    if match:
        parts = match.group(1).split("/")
        return f"ASoC: {parts[-1].replace('.c', '').replace('-', '_')}"
    match = re.search(r"diff --git a/(sound/[^/]+)", content)
    if match:
        return "ALSA"
    return "kernel"


def fix_commit_subject(content: str, subsystem: str) -> str:
    pattern = r"(Subject: \[PATCH[^\]]*\] )(?!" + re.escape(subsystem.split(":")[0]) + r")(.*)"
    replacement = r"\1" + subsystem + r": \2"
    return re.sub(pattern, replacement, content)


def add_signed_off_by(content: str) -> str:
    if "Signed-off-by:" in content:
        return content
    if "---" in content:
        parts = content.split("---", 1)
        return parts[0].rstrip() + "\nSigned-off-by: Author <author@example.com>\n---" + parts[1]
    return content + "\nSigned-off-by: Author <author@example.com>\n"


def add_changelog_section(content: str) -> str:
    if "*** changes in" in content.lower():
        return content
    if "---" in content:
        parts = content.split("---", 1)
        changelog = "\n\nChanges in this version:\n  - [describe changes from previous version]\n"
        return parts[0] + changelog + "---" + parts[1]
    return content


def add_link_section(content: str) -> str:
    if "Link:" in content:
        return content
    if "---" in content:
        parts = content.split("---", 1)
        link = "\nLink: [URL to previous version]\n"
        return parts[0] + link + "---" + parts[1]
    return content


__all__ = [
    "aryabhata_apply_fixes",
    "format_issues_for_aryabhata",
    "parse_fixed_patches",
    "parse_fix_summary",
    "apply_rule_based_fixes",
]
