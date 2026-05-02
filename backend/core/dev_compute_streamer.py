"""
Streams dev-compute execution output to UI in real-time.
Users see exactly what patchwise is doing on dev-compute.
"""

from __future__ import annotations

import asyncio
import re
import shlex
from typing import AsyncGenerator


class DevComputeStreamer:
    def __init__(self, ssh_pool, websocket_manager):
        self.ssh = ssh_pool
        self.ws = websocket_manager

    async def stream_command(
        self,
        session_id: str,
        agent: str,
        command: str,
        screen_name: str,
    ) -> AsyncGenerator[str, None]:
        log_file = f"/tmp/patchwise/{agent}/{session_id}/exec.log"
        quoted_log = shlex.quote(log_file)
        await self.ssh.exec(agent, session_id, f"screen -S {shlex.quote(screen_name)} -X logfile {quoted_log}")
        await self.ssh.exec(agent, session_id, f"screen -S {shlex.quote(screen_name)} -X log on")
        await self.ssh.exec(agent, session_id, f"screen -S {shlex.quote(screen_name)} -X stuff {shlex.quote(command + chr(10))}")

        async for line in self._tail_log(log_file, session_id, agent, screen_name):
            yield line

    async def _tail_log(
        self,
        log_file: str,
        session_id: str,
        agent: str,
        screen_name: str,
    ) -> AsyncGenerator[str, None]:
        last_size = 0
        max_wait = 300

        for _ in range(max_wait * 10):
            size_result = await self.ssh.exec(
                agent,
                session_id,
                f"wc -c < {shlex.quote(log_file)} 2>/dev/null || echo 0",
                timeout=10,
            )
            try:
                current_size = int((size_result.stdout or "0").strip() or 0)
            except ValueError:
                current_size = 0

            if current_size > last_size:
                new_content = await self.ssh.exec(
                    agent,
                    session_id,
                    f"tail -c +{last_size + 1} {shlex.quote(log_file)}",
                    timeout=10,
                )
                for line in (new_content.stdout or "").splitlines():
                    if not line.strip():
                        continue
                    line_type = self._classify_line(line)
                    progress = self._extract_progress(line)
                    await self.ws.emit(
                        session_id,
                        {
                            "type": "dev_compute_output",
                            "session_id": session_id,
                            "agent": agent,
                            "line": line.strip(),
                            "line_type": line_type,
                            "progress": progress,
                        },
                    )
                    yield line
                last_size = current_size

            marker = await self._check_marker(agent, session_id, log_file)
            if "command_done" in marker:
                break

            # Stop if screen session no longer exists.
            alive = await self.ssh.exec(
                agent,
                session_id,
                f"screen -ls 2>/dev/null | grep -q {shlex.quote(screen_name)} && echo YES || echo NO",
                timeout=10,
            )
            if "NO" in (alive.stdout or ""):
                break

            await asyncio.sleep(0.1)

    def _classify_line(self, line: str) -> str:
        line_lower = line.lower()
        if line.startswith("$") or line.startswith(">>>"):
            return "command"
        if "error:" in line_lower or "exception" in line_lower:
            return "error"
        if "warning:" in line_lower:
            return "warning"
        if any(word in line_lower for word in ["success", "lgtm", "passed", "done"]):
            return "success"
        if "%" in line or "progress" in line_lower:
            return "progress"
        return "info"

    def _extract_progress(self, line: str) -> int:
        match = re.search(r"(\d+)\s*%", line)
        if match:
            return int(match.group(1))
        lower = line.lower()
        if "reviewing commit" in lower:
            return 50
        if "lgtm" in lower or "complete" in lower:
            return 100
        return 0

    async def _check_marker(self, agent: str, session_id: str, log_file: str) -> str:
        result = await self.ssh.exec(
            agent,
            session_id,
            f"tail -5 {shlex.quote(log_file)} 2>/dev/null",
            timeout=10,
        )
        return result.stdout or ""
