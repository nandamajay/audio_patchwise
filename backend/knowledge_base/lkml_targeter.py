from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any, Optional

DEFAULT_AUDIO_TARGETS = {
    "mailing_lists": [
        {
            "id": "alsa-devel",
            "name": "alsa-devel",
            "email": "alsa-devel@alsa-project.org",
            "lore_url": "https://lore.kernel.org/alsa-devel/",
            "description": "Primary ALSA development list",
            "subsystem": "audio",
        },
        {
            "id": "linux-sound",
            "name": "linux-sound",
            "email": "linux-sound@vger.kernel.org",
            "lore_url": "https://lore.kernel.org/linux-sound/",
            "description": "Linux sound subsystem",
            "subsystem": "audio",
        },
        {
            "id": "linux-kernel",
            "name": "linux-kernel",
            "email": "linux-kernel@vger.kernel.org",
            "lore_url": "https://lore.kernel.org/linux-kernel/",
            "description": "Main Linux kernel list",
            "subsystem": "general",
        },
        {
            "id": "linux-audio-dev",
            "name": "linux-audio-dev",
            "email": "linux-audio-dev@lists.linuxaudio.org",
            "lore_url": "https://lore.kernel.org/linux-audio-dev/",
            "description": "Linux audio development",
            "subsystem": "audio",
        },
        {
            "id": "patches",
            "name": "patches",
            "email": "patches@alsa-project.org",
            "lore_url": "https://lore.kernel.org/patches/",
            "description": "ALSA patches tracker",
            "subsystem": "audio",
        },
    ],
    "maintainers": [
        {
            "id": "tiwai",
            "name": "Takashi Iwai",
            "email": "tiwai@suse.de",
            "role": "ALSA Maintainer",
            "subsystem": "audio",
        },
        {
            "id": "broonie",
            "name": "Mark Brown",
            "email": "broonie@kernel.org",
            "role": "ASoC Maintainer",
            "subsystem": "asoc",
        },
        {
            "id": "perex",
            "name": "Jaroslav Kysela",
            "email": "perex@perex.cz",
            "role": "ALSA Core Maintainer",
            "subsystem": "audio",
        },
        {
            "id": "lgirdwood",
            "name": "Liam Girdwood",
            "email": "lgirdwood@gmail.com",
            "role": "ASoC Co-Maintainer",
            "subsystem": "asoc",
        },
    ],
}


class LKMLTargeter:
    """
    Identify relevant mailing lists and maintainers for a patch.
    Uses get_maintainer.pl when available and falls back to heuristics.
    """

    def __init__(self, kernel_path: Optional[str] = None):
        self.kernel_path = kernel_path or "/workspace/linux"
        self.get_maintainer_script = f"{self.kernel_path}/scripts/get_maintainer.pl"

    async def auto_detect_from_patch(self, patch_content: str) -> dict[str, Any]:
        import os
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".patch", delete=False) as temp_file:
            temp_file.write(patch_content)
            temp_path = temp_file.name

        result: dict[str, Any] = {"mailing_lists": [], "maintainers": [], "source": "heuristic"}

        if Path(self.get_maintainer_script).exists():
            try:
                proc = await asyncio.create_subprocess_exec(
                    "perl",
                    self.get_maintainer_script,
                    "--nogit",
                    "--nogit-fallback",
                    "--norolestats",
                    temp_path,
                    cwd=self.kernel_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
                output = stdout.decode()
                parsed = self._parse_get_maintainer_output(output)
                if parsed["mailing_lists"] or parsed["maintainers"]:
                    parsed["source"] = "get_maintainer.pl"
                    result = parsed
            except Exception:
                pass

        if not result["mailing_lists"]:
            result = self._heuristic_detect(patch_content)
            result["source"] = "heuristic"

        os.unlink(temp_path)
        return result

    def _parse_get_maintainer_output(self, output: str) -> dict[str, Any]:
        maintainers: list[dict[str, Any]] = []
        mailing_lists: list[dict[str, Any]] = []

        for raw_line in output.strip().split("\n"):
            line = raw_line.strip()
            if not line:
                continue

            email_match = re.search(r"<([^>]+@[^>]+)>", line)
            if not email_match:
                continue

            email = email_match.group(1)
            name = line.split("<")[0].strip().rstrip("(").strip()
            role_match = re.search(r"\(([^)]+)\)", line)
            role = role_match.group(1) if role_match else "Maintainer"

            if "@vger.kernel.org" in email or "@alsa-project.org" in email or "@lists." in email:
                list_id = email.split("@")[0]
                mailing_lists.append(
                    {
                        "id": list_id,
                        "name": list_id,
                        "email": email,
                        "lore_url": f"https://lore.kernel.org/{list_id}/",
                        "description": role,
                        "subsystem": "detected",
                    }
                )
            else:
                maintainers.append(
                    {
                        "id": email.split("@")[0],
                        "name": name,
                        "email": email,
                        "role": role,
                        "subsystem": "detected",
                    }
                )

        return {"mailing_lists": mailing_lists, "maintainers": maintainers}

    def _heuristic_detect(self, patch_content: str) -> dict[str, Any]:
        audio_paths = ["sound/", "drivers/sound/", "include/sound/", "Documentation/sound/"]
        asoc_paths = ["sound/soc/", "sound/codecs/"]

        is_audio = any(path in patch_content for path in audio_paths)
        is_asoc = any(path in patch_content for path in asoc_paths)

        mailing_lists: list[dict[str, Any]] = []
        maintainers: list[dict[str, Any]] = []

        if is_audio:
            mailing_lists = [
                item
                for item in DEFAULT_AUDIO_TARGETS["mailing_lists"]
                if item["subsystem"] in ["audio", "general"]
            ]
            maintainers = [
                item
                for item in DEFAULT_AUDIO_TARGETS["maintainers"]
                if item["subsystem"] in ["audio"]
            ]

        if is_asoc:
            for item in DEFAULT_AUDIO_TARGETS["mailing_lists"]:
                if item["id"] == "alsa-devel" and item not in mailing_lists:
                    mailing_lists.append(item)
            for item in DEFAULT_AUDIO_TARGETS["maintainers"]:
                if item["subsystem"] == "asoc" and item not in maintainers:
                    maintainers.append(item)

        return {"mailing_lists": mailing_lists, "maintainers": maintainers}

    def get_all_targets(self) -> dict[str, Any]:
        return DEFAULT_AUDIO_TARGETS
