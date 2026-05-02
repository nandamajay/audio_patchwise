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
        # Pull detailed review discussion evidence (first page only for bounded latency).
        issue_comments_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{number}/comments?per_page=30"
        review_comments_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}/comments?per_page=30"
        issue_comments: list[dict[str, Any]] = []
        review_comments: list[dict[str, Any]] = []
        ic_resp = await client.get(issue_comments_url)
        if ic_resp.status_code == 200 and isinstance(ic_resp.json(), list):
            issue_comments = ic_resp.json()
        rc_resp = await client.get(review_comments_url)
        if rc_resp.status_code == 200 and isinstance(rc_resp.json(), list):
            review_comments = rc_resp.json()
        metadata["issue_comment_count_loaded"] = len(issue_comments)
        metadata["review_comment_count_loaded"] = len(review_comments)
        metadata["issue_comment_snippets"] = [
            {
                "author": ((c.get("user") or {}).get("login") or ""),
                "body": str(c.get("body") or "")[:500],
                "created_at": c.get("created_at"),
                "url": c.get("html_url"),
            }
            for c in issue_comments[:12]
        ]
        metadata["review_comment_snippets"] = [
            {
                "author": ((c.get("user") or {}).get("login") or ""),
                "body": str(c.get("body") or "")[:500],
                "path": c.get("path"),
                "position": c.get("position"),
                "created_at": c.get("created_at"),
                "url": c.get("html_url"),
            }
            for c in review_comments[:20]
        ]
        evidence.append(
            {
                "source": "github_pr_reviews",
                "source_url": review_comments_url,
                "note": f"Fetched {len(review_comments)} review comments and {len(issue_comments)} issue comments",
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
    version_match = re.search(r"\[PATCH\s+v(\d+)", patch_text, re.IGNORECASE)
    current_version = int(version_match.group(1)) if version_match else 1
    history = await fetch_version_history(
        patch_content=patch_text,
        input_url=lore_url,
        subsystem=subsystem or "alsa-devel",
    )
    thread = await fetch_lore_thread(lore_url, subsystem or "alsa-devel")
    history_verified = _verify_lore_history(
        current_version=current_version,
        history=history,
        thread=thread or {},
        current_url=lore_url,
    )
    metadata = {
        "lore_url": lore_url,
        "history": history,
        "history_verified": history_verified,
        "current_version": current_version,
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
    if history.get("found") and history_verified:
        evidence.append(
            {
                "source": "lore_history",
                "source_url": history.get("prev_version_url"),
                "note": f"Detected prior version chain v{history.get('version', 1)}",
            }
        )
    elif history.get("found") and not history_verified:
        history["found"] = False
        history["degrade_message"] = (
            "History chain detected but could not verify a reliable vN-1 linkage from evidence."
        )
        evidence.append(
            {
                "source": "lore_history",
                "source_url": history.get("prev_version_url"),
                "note": "History chain exists but is marked unverified",
            }
        )
    return InputBundle(
        input_type="lore_url",
        input_ref=lore_url,
        patch_text=patch_text,
        metadata=metadata,
        evidence=evidence,
    )


def _verify_lore_history(
    *,
    current_version: int,
    history: dict[str, Any],
    thread: dict[str, Any],
    current_url: str,
) -> bool:
    if current_version <= 1:
        return False
    if not isinstance(history, dict) or not history.get("found"):
        return False
    prev_url = str(history.get("prev_version_url") or "")
    replies = history.get("reviewer_comments") if isinstance(history.get("reviewer_comments"), list) else []
    patches = history.get("prev_patches") if isinstance(history.get("prev_patches"), list) else []
    thread_comments = thread.get("comments") if isinstance(thread.get("comments"), list) else []
    # Verified when any independent review interaction exists.
    if replies or thread_comments:
        return True
    # If URL differs from current URL we treat as historical chain.
    if prev_url and prev_url.rstrip("/") != current_url.rstrip("/"):
        return True
    # If thread contains at least two patch-like messages, treat as series context.
    if len(patches) >= 2:
        return True
    return False


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
