"""
Input processor for patch sources (RAW, LORE URL, GERRIT URL).
Detects URLs and can fetch content before handing to CHANAKYA.
"""
# input_processor: URL detection + fetch helper
from __future__ import annotations

import re
from typing import Literal, Tuple

import httpx

InputType = Literal["LORE_URL", "GERRIT_URL", "RAW_PATCH", "FILE"]

LORE_URL_PATTERN = re.compile(r"https?://lore\.kernel\.org/[^\s]+", re.IGNORECASE)
GERRIT_URL_PATTERN = re.compile(r"https?://[a-z0-9.-]*gerrit[^\s]*", re.IGNORECASE)


def detect_input_type(text: str) -> InputType:
    trimmed = (text or "").strip()
    if LORE_URL_PATTERN.search(trimmed):
        return "LORE_URL"
    if GERRIT_URL_PATTERN.search(trimmed):
        return "GERRIT_URL"
    if trimmed.startswith("From ") or "diff --git" in trimmed:
        return "RAW_PATCH"
    return "FILE"


async def fetch_patch_content(url: str) -> str:
    """Fetch raw patch content from known URL types."""
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text


async def process_input(text: str) -> Tuple[InputType, str]:
    """Detect input type and return normalized patch content."""
    input_type = detect_input_type(text)
    if input_type in {"LORE_URL", "GERRIT_URL"}:
        content = await fetch_patch_content(text.strip())
        return input_type, content
    return input_type, text
