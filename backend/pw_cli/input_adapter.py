from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from agents.version_intelligence import fetch_lore_thread, fetch_version_history
from core.input_processor import fetch_patch_content


LORE_URL_RE = re.compile(r"^https?://lore\.kernel\.org/.+$", re.IGNORECASE)
GITHUB_PR_RE = re.compile(
    r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<number>\d+)",
    re.IGNORECASE,
)


@dataclass
class InputBundle:
    input_type: str
    input_ref: str
    patch_text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    evidence: list[dict[str, Any]] = field(default_factory=list)


def _collect_patch_from_path(path: str) -> str:
    target = Path(path)
    if target.is_file():
        return target.read_text(encoding="utf-8", errors="replace")
    if target.is_dir():
        chunks: list[str] = []
        files = sorted(
            [p for p in target.iterdir() if p.suffix in {".patch", ".diff", ".txt"} and p.is_file()]
        )
        for file_path in files:
            chunks.append(file_path.read_text(encoding="utf-8", errors="replace"))
        return "\n\n".join(chunks)
    return path


async def _fetch_github_pr(pr_url: str) -> InputBundle:
    match = GITHUB_PR_RE.match(pr_url.strip())
    if not match:
        return InputBundle(input_type="raw", input_ref=pr_url, patch_text=pr_url)
    owner = match.group("owner")
    repo = match.group("repo")
    number = match.group("number")
    patch_url = f"https://patch-diff.githubusercontent.com/raw/{owner}/{repo}/pull/{number}.patch"
    token = os.getenv("GITHUB_TOKEN", "").strip()
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    metadata: dict[str, Any] = {
        "owner": owner,
        "repo": repo,
        "number": int(number),
        "patch_url": patch_url,
    }
    patch_text = ""
    evidence: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers=headers) as client:
        patch_resp = await client.get(patch_url)
        patch_resp.raise_for_status()
        patch_text = patch_resp.text
        evidence.append(
            {
                "source": "github_pr",
                "source_url": patch_url,
                "note": "Fetched PR patch content",
            }
        )
        api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}"
        api_resp = await client.get(api_url)
        if api_resp.status_code == 200:
            payload = api_resp.json()
            metadata["title"] = payload.get("title", "")
            metadata["state"] = payload.get("state", "")
            metadata["author"] = (payload.get("user") or {}).get("login", "")
            metadata["merged"] = bool(payload.get("merged"))
            metadata["comments"] = int(payload.get("comments", 0) or 0)
            metadata["review_comments"] = int(payload.get("review_comments", 0) or 0)
            evidence.append(
                {
                    "source": "github_pr",
                    "source_url": api_url,
                    "note": "Fetched PR metadata and review counters",
                }
            )
    return InputBundle(
        input_type="github_pr",
        input_ref=pr_url,
        patch_text=patch_text,
        metadata=metadata,
        evidence=evidence,
    )


async def _fetch_lore(lore_url: str, subsystem: str) -> InputBundle:
    patch_text = await fetch_patch_content(lore_url)
    history = await fetch_version_history(
        patch_content=patch_text,
        input_url=lore_url,
        subsystem=subsystem or "alsa-devel",
    )
    thread = await fetch_lore_thread(lore_url, subsystem or "alsa-devel")
    metadata = {
        "lore_url": lore_url,
        "history": history,
        "thread_comment_count": len((thread or {}).get("comments") or []),
        "thread_patch_count": len((thread or {}).get("patches") or []),
    }
    evidence: list[dict[str, Any]] = [
        {
            "source": "lore",
            "source_url": lore_url,
            "note": "Fetched lore patch content",
        }
    ]
    if history.get("found"):
        evidence.append(
            {
                "source": "lore_history",
                "source_url": history.get("prev_version_url"),
                "note": f"Detected prior version chain v{history.get('version', 1)}",
            }
        )
    return InputBundle(
        input_type="lore_url",
        input_ref=lore_url,
        patch_text=patch_text,
        metadata=metadata,
        evidence=evidence,
    )


async def resolve_input_bundle(input_value: str, input_type: str, subsystem: str) -> InputBundle:
    input_value = (input_value or "").strip()
    mode = (input_type or "auto").strip().lower()

    if mode == "file":
        content = _collect_patch_from_path(input_value)
        return InputBundle(
            input_type="file",
            input_ref=input_value,
            patch_text=content,
            evidence=[{"source": "file", "source_url": input_value, "note": "Read patch from path"}],
        )
    if mode == "raw":
        return InputBundle(input_type="raw", input_ref="inline", patch_text=input_value)

    if LORE_URL_RE.match(input_value):
        return await _fetch_lore(input_value, subsystem=subsystem)
    if GITHUB_PR_RE.match(input_value):
        return await _fetch_github_pr(input_value)
    if Path(input_value).exists():
        content = _collect_patch_from_path(input_value)
        return InputBundle(
            input_type="file",
            input_ref=input_value,
            patch_text=content,
            evidence=[{"source": "file", "source_url": input_value, "note": "Read patch from path"}],
        )

    return InputBundle(input_type="raw", input_ref="inline", patch_text=input_value)

