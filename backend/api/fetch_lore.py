from __future__ import annotations

import email
import gzip
import re
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class LoreFetchRequest(BaseModel):
    url: str


class PatchItem(BaseModel):
    index: int
    subject: str
    content: str
    message_id: str
    author: str
    date: str
    size: int


class LoreFetchResponse(BaseModel):
    patches: list[PatchItem]
    series_title: str
    version: int
    thread_count: int
    prev_version_url: Optional[str]
    mbox_url: str


@router.post("/api/fetch-lore", response_model=LoreFetchResponse)
async def fetch_lore_patches(request: LoreFetchRequest) -> LoreFetchResponse:
    """
    Fetch all patches from a lore.kernel.org URL.

    Handles:
    - Single patch URLs
    - Cover letter URLs
    - Thread URLs

    Uses thread mbox download to gather full series when possible.
    """
    url = request.url.strip()

    msg_id_pattern = r"(\d{14}\.\d+-\d+-[^/\s]+)"
    match = re.search(msg_id_pattern, url)

    if not match:
        raise HTTPException(
            status_code=400,
            detail=(
                "Could not extract message ID from URL. "
                "Expected format: https://lore.kernel.org/*/YYYYMMDDHHMMSS.NNNNNN-N-user@host/"
            ),
        )

    msg_id_base = match.group(1)
    list_match = re.search(r"lore\.kernel\.org/([^/]+)/", url)
    list_name = list_match.group(1) if list_match else "all"

    # Use full message-id stem to resolve the thread anchor reliably.
    thread_url = f"https://lore.kernel.org/{list_name}/{msg_id_base}/"
    mbox_url = f"{thread_url}t.mbox.gz"

    patches: list[PatchItem] = []
    thread_count = 0
    prev_version_url = None
    series_title = "Unknown Series"
    version = 1

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(mbox_url)

            if resp.status_code == 200:
                try:
                    content = gzip.decompress(resp.content)
                except Exception:
                    content = resp.content

                decoded = content.decode("utf-8", errors="replace")
                patch_index = 0

                for msg_str in split_mbox(decoded):
                    try:
                        msg = email.message_from_string(msg_str)
                        subject = msg.get("Subject", "")
                        from_addr = msg.get("From", "")
                        date = msg.get("Date", "")
                        msg_id = msg.get("Message-ID", "").strip("<>")
                        thread_count += 1

                        if "[PATCH" not in subject.upper():
                            continue

                        body = get_email_body(msg)

                        if "---" not in body and "diff --git" not in body:
                            if "0/" in subject:
                                patches.insert(
                                    0,
                                    PatchItem(
                                        index=0,
                                        subject=subject,
                                        content=body,
                                        message_id=msg_id,
                                        author=from_addr,
                                        date=date,
                                        size=len(body),
                                    ),
                                )
                            continue

                        v_match = re.search(r"\[PATCH\s+v(\d+)", subject, re.IGNORECASE)
                        if v_match:
                            version = int(v_match.group(1))

                        if patch_index == 0:
                            title_match = re.sub(r"\[PATCH[^\]]*\]\s*", "", subject).strip()
                            series_title = title_match or series_title

                        link_match = re.search(r"Link:\s*(https://lore\.kernel\.org/[^\s]+)", body)
                        if link_match and not prev_version_url:
                            prev_version_url = link_match.group(1)

                        patch_index += 1
                        patches.append(
                            PatchItem(
                                index=patch_index,
                                subject=subject,
                                content=body,
                                message_id=msg_id,
                                author=from_addr,
                                date=date,
                                size=len(body),
                            )
                        )
                    except Exception:
                        continue
            else:
                single_url = url.rstrip("/") + "/raw"
                single_resp = await client.get(single_url)
                if single_resp.status_code == 200:
                    body = single_resp.text
                    patches.append(
                        PatchItem(
                            index=1,
                            subject="Fetched patch",
                            content=body,
                            message_id=msg_id_base,
                            author="",
                            date="",
                            size=len(body),
                        )
                    )
                else:
                    raise HTTPException(
                        status_code=503,
                        detail="lore.kernel.org unreachable. Proceeding with standalone review.",
                    )

    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail="Timeout fetching from lore.kernel.org. Check connection or try again.",
        ) from exc

    if not patches:
        raise HTTPException(
            status_code=404,
            detail="No patches found at this URL. Check the link and try again.",
        )

    return LoreFetchResponse(
        patches=patches,
        series_title=series_title,
        version=version,
        thread_count=thread_count,
        prev_version_url=prev_version_url,
        mbox_url=mbox_url,
    )


def split_mbox(content: str) -> list[str]:
    """Split mbox content into individual messages."""
    messages: list[str] = []
    current: list[str] = []
    for line in content.split("\n"):
        if line.startswith("From ") and current:
            messages.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        messages.append("\n".join(current))
    return messages


def get_email_body(msg) -> str:
    """Extract body text from email message."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode("utf-8", errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            return payload.decode("utf-8", errors="replace")
        return str(msg.get_payload())
    return ""
