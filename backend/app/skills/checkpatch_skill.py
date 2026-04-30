from __future__ import annotations

import subprocess
from tempfile import NamedTemporaryFile


def run_checkpatch(patch_text: str) -> dict:
    """Run checkpatch.pl if available; otherwise return a skipped result."""

    cmd = ["scripts/checkpatch.pl", "--no-tree", "--strict"]

    with NamedTemporaryFile(mode="w+", suffix=".patch", delete=True) as tmp:
        tmp.write(patch_text)
        tmp.flush()
        try:
            result = subprocess.run(
                cmd + [tmp.name],
                check=False,
                text=True,
                capture_output=True,
            )
        except FileNotFoundError:
            return {
                "status": "skipped",
                "reason": "checkpatch.pl not found in current environment",
                "output": "",
            }

    return {
        "status": "ok" if result.returncode == 0 else "issues",
        "returncode": result.returncode,
        "output": result.stdout + result.stderr,
    }
