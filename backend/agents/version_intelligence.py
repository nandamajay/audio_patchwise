from __future__ import annotations

import re
from typing import Any, Optional

import httpx


def split_mbox(content: str) -> list[str]:
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


def get_email_body_str(msg) -> str:
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


def parse_search_results(html: str, prev_version: int) -> Optional[str]:
    del prev_version
    matches = re.findall(r'href="(https://lore\.kernel\.org/[^"\s]+)"', html)
    for link in matches:
        if "/all/" in link:
            continue
        return link
    return matches[0] if matches else None


async def fetch_version_history(
    patch_content: str,
    input_url: str | None = None,
    subsystem: str = "alsa-devel",
) -> dict[str, Any]:
    """
    Fetch version history for a patch series.

    Strategy:
    1. Check Link header in patch.
    2. Search lore by subject for vN-1.
    3. Try provided input URL.
    4. Soft degrade with a user hint.
    """
    result: dict[str, Any] = {
        "found": False,
        "version": 1,
        "prev_version_url": None,
        "prev_patches": [],
        "reviewer_comments": [],
        "degrade_message": None,
    }

    v_match = re.search(r"\[PATCH\s+v(\d+)", patch_content, re.IGNORECASE)
    if v_match:
        result["version"] = int(v_match.group(1))

    if result["version"] == 1:
        result["degrade_message"] = "v1 patch - no prior version history. Reviewing standalone."
        return result

    link_match = re.search(r"Link:\s*(https://lore\.kernel\.org/[^\s]+)", patch_content)
    if link_match:
        prev_url = link_match.group(1)
        try:
            fetched = await fetch_lore_thread(prev_url, subsystem)
            if fetched:
                result["found"] = True
                result["prev_version_url"] = prev_url
                result["prev_patches"] = fetched["patches"]
                result["reviewer_comments"] = fetched["comments"]
                return result
        except Exception as exc:
            print(f"[WARN] Link fetch failed: {exc}")

    subject_match = re.search(r"Subject: \[PATCH[^\]]*\]\s*(.*)", patch_content)
    if subject_match:
        subject = subject_match.group(1).strip()
        prev_version = result["version"] - 1
        search_subject = re.sub(r"^[^:]+:\s*", "", subject)

        try:
            search_url = f"https://lore.kernel.org/{subsystem}/?q={search_subject}+v{prev_version}&x=m"
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(search_url)
                if resp.status_code == 200:
                    found_url = parse_search_results(resp.text, prev_version)
                    if found_url:
                        fetched = await fetch_lore_thread(found_url, subsystem)
                        if fetched:
                            result["found"] = True
                            result["prev_version_url"] = found_url
                            result["prev_patches"] = fetched["patches"]
                            result["reviewer_comments"] = fetched["comments"]
                            return result
        except Exception as exc:
            print(f"[WARN] Subject search failed: {exc}")

    if input_url:
        try:
            fetched = await fetch_lore_thread(input_url, subsystem)
            if fetched:
                result["found"] = True
                result["prev_version_url"] = input_url
                result["prev_patches"] = fetched["patches"]
                result["reviewer_comments"] = fetched["comments"]
                return result
        except Exception as exc:
            print(f"[WARN] Direct URL fetch failed: {exc}")

    result["degrade_message"] = (
        f"Could not find v{result['version'] - 1} thread automatically. "
        f"Please provide the previous version link for full context, "
        f"or we'll proceed with standalone v{result['version']} review."
    )
    result["ask_user"] = True
    return result


async def fetch_lore_thread(url: str, subsystem: str) -> dict[str, Any] | None:
    """Fetch and parse a lore.kernel.org thread."""
    del subsystem

    if not url.endswith(".mbox.gz"):
        mbox_url = url.rstrip("/") + "/t.mbox.gz"
    else:
        mbox_url = url

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(mbox_url)
        if resp.status_code != 200:
            return None

        import email as email_lib
        import gzip

        try:
            content = gzip.decompress(resp.content).decode("utf-8", errors="replace")
        except Exception:
            content = resp.content.decode("utf-8", errors="replace")

        messages = split_mbox(content)
        patches: list[dict[str, Any]] = []
        comments: list[dict[str, Any]] = []

        for msg_str in messages:
            msg = email_lib.message_from_string(msg_str)
            subject = msg.get("Subject", "")
            from_addr = msg.get("From", "")
            body = get_email_body_str(msg)

            if "[PATCH" in subject:
                patches.append(
                    {
                        "subject": subject,
                        "content": body,
                        "author": from_addr,
                    }
                )
            elif body.strip() and not subject.startswith("Re: [PATCH 0"):
                comments.append(
                    {
                        "author": from_addr,
                        "subject": subject,
                        "body": body,
                        "is_maintainer": is_known_maintainer(from_addr),
                    }
                )

        return {"patches": patches, "comments": comments}


def is_known_maintainer(email_addr: str) -> bool:
    known_maintainers = [
        "tiwai@suse.de",
        "broonie@kernel.org",
        "perex@perex.cz",
        "alsa-devel@alsa-project.org",
        "lgirdwood@gmail.com",
    ]
    return any(m in email_addr for m in known_maintainers)
