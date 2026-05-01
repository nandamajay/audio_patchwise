from __future__ import annotations

import importlib
from typing import Any

__all__ = [
    "ARYABHATA_SYSTEM_PROMPT",
    "AryabhataAgent",
    "ChanakyaAgent",
    "CHANAKYA_SYSTEM_PROMPT",
    "CHANAKYA_ISSUE_FORMAT_PROMPT",
    "ChanakyaIssueParser",
]


def __getattr__(name: str) -> Any:
    # Lazy imports prevent circular import during app startup.
    if name == "ARYABHATA_SYSTEM_PROMPT":
        return importlib.import_module("agents.aryabhata_agent").ARYABHATA_SYSTEM_PROMPT
    if name == "AryabhataAgent":
        return importlib.import_module("agents.aryabhata_agent").AryabhataAgent
    if name == "ChanakyaAgent":
        return importlib.import_module("agents.chanakya_agent").ChanakyaAgent
    if name in {"CHANAKYA_SYSTEM_PROMPT", "CHANAKYA_ISSUE_FORMAT_PROMPT"}:
        module = importlib.import_module("agents.chanakya_agent")
        return getattr(module, name)
    if name == "ChanakyaIssueParser":
        return importlib.import_module("agents.chanakya_parser").ChanakyaIssueParser
    raise AttributeError(f"module 'agents' has no attribute '{name}'")
