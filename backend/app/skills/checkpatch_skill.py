from __future__ import annotations

import os
from pathlib import Path
import subprocess
from tempfile import NamedTemporaryFile


def _resolve_checkpatch() -> list[str] | None:
    env_path = os.environ.get("CHECKPATCH_PATH", "").strip()
    candidates = [
        env_path,
        "scripts/checkpatch.pl",
        "checkpatch.pl",
        "/tools/checkpatch.pl",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        if Path(candidate).is_file():
            return [candidate]
    return None


def run_checkpatch(patch_text: str) -> dict:
    """Run checkpatch.pl if available; otherwise return a skipped result."""
    checkpatch_cmd = _resolve_checkpatch()
    if checkpatch_cmd is None:
        return {
            "status": "skipped",
            "reason": "checkpatch.pl not found in current environment",
            "output": "",
        }

    with NamedTemporaryFile(mode="w+", suffix=".patch", delete=True) as tmp:
        tmp.write(patch_text)
        tmp.flush()
        result = subprocess.run(
            checkpatch_cmd + ["--no-tree", "--strict", tmp.name],
            check=False,
            text=True,
            capture_output=True,
        )

    return {
        "status": "ok" if result.returncode == 0 else "issues",
        "returncode": result.returncode,
        "output": result.stdout + result.stderr,
    }
