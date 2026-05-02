from __future__ import annotations

import os
import re
from pathlib import PurePosixPath
from typing import Iterable


def extract_patch_paths(patch_text: str) -> list[str]:
    paths: list[str] = []
    for line in patch_text.splitlines():
        m = re.match(r"^diff --git a/(.+?) b/(.+)$", line)
        if m:
            paths.append(m.group(2))
    return paths


def resolve_kernel_path(candidate_root: str | None = None) -> str:
    root = candidate_root or os.getenv(
        "DEV_COMPUTE_KERNEL_PATH",
        "/local/mnt/workspace/upstream_patches/xo_sd_LPI/linux-next",
    )
    return root


def unresolved_paths(patch_paths: Iterable[str], kernel_root: str | None = None) -> list[str]:
    root = resolve_kernel_path(kernel_root)
    missing: list[str] = []
    for path in patch_paths:
        full = PurePosixPath(root) / path
        if not os.path.exists(str(full)):
            missing.append(path)
    return missing
