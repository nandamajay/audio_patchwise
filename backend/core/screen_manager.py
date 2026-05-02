from __future__ import annotations

import logging
import os
import shlex
from typing import Optional

from core.ssh_pool import AgentRole, ExecutionMode, ssh_pool

logger = logging.getLogger("uvicorn.error")


class ScreenManager:
    """
    GNU Screen lifecycle helper for per-agent sessions.
    Screen survives SSH drops and can be re-attached on reconnect.
    """

    def __init__(self):
        self.prefix = os.getenv("SCREEN_SESSION_PREFIX", "pw")
        self.cleanup_on_complete = os.getenv("SCREEN_CLEANUP_ON_COMPLETE", "true").lower() in {
            "1",
            "true",
            "yes",
        }

    def _name(self, agent: AgentRole, session_id: str) -> str:
        return f"{self.prefix}_{agent.value}_{session_id}"

    async def create_screen(self, agent: AgentRole, session_id: str) -> str:
        name = self._name(agent, session_id)
        await ssh_pool.ensure_work_dir(agent, session_id)
        # Persistent detached shell session (survives command completion and SSH reconnects).
        cmd = f"screen -dmS {shlex.quote(name)} bash"
        await ssh_pool.exec(agent, session_id, cmd, timeout=20)
        await ssh_pool.save_screen_state(agent, session_id, name)
        logger.info("[Screen] created %s", name)
        return name

    async def run_in_screen(self, agent: AgentRole, session_id: str, cmd: str) -> str:
        name = self._name(agent, session_id)
        exists = await self.screen_exists(name, agent, session_id)
        if not exists:
            await self.create_screen(agent, session_id)
        safe_cmd = cmd.replace("'", "'\"'\"'")
        stuff_cmd = f"screen -S {shlex.quote(name)} -X stuff '{safe_cmd}\\n'"
        await ssh_pool.exec(agent, session_id, stuff_cmd, timeout=30)
        return name

    async def screen_exists(self, name: str, agent: Optional[AgentRole] = None, session_id: str = "") -> bool:
        run_agent = agent or AgentRole.CHANAKYA
        result = await ssh_pool.exec(
            run_agent,
            session_id or "health",
            f"screen -ls 2>/dev/null | grep -q {shlex.quote(name)} && echo YES || echo NO",
            timeout=10,
        )
        return "YES" in result.stdout

    async def reattach_screen(self, name: str, agent: AgentRole, session_id: str) -> str:
        # Non-interactive: dump recent output as a lightweight reattach substitute.
        return await self.get_screen_output(name, agent, session_id)

    async def get_screen_output(self, name: str, agent: AgentRole, session_id: str) -> str:
        log_path = f"/tmp/{name}.log"
        cmd = (
            f"screen -S {shlex.quote(name)} -X hardcopy -h {shlex.quote(log_path)}; "
            f"tail -n 120 {shlex.quote(log_path)} 2>/dev/null || true"
        )
        result = await ssh_pool.exec(agent, session_id, cmd, timeout=15)
        return result.stdout

    async def cleanup_screen(self, session_id: str) -> None:
        for agent in (AgentRole.CHANAKYA, AgentRole.ARYABHATA):
            name = self._name(agent, session_id)
            await ssh_pool.exec(
                agent,
                session_id,
                f"screen -S {shlex.quote(name)} -X quit 2>/dev/null || true",
                timeout=10,
            )
            logger.info("[Screen] cleaned %s", name)

    async def list_screens(self) -> list[str]:
        probe_agent = AgentRole.CHANAKYA
        result = await ssh_pool.exec(
            probe_agent,
            "health",
            "screen -ls 2>/dev/null | grep pw_ | awk '{print $1}' || true",
            timeout=10,
        )
        screens = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return screens

    async def reattach_after_reconnect(self, session_id: str) -> dict[str, str]:
        recovered: dict[str, str] = {}
        for agent in (AgentRole.CHANAKYA, AgentRole.ARYABHATA):
            name = self._name(agent, session_id)
            if await self.screen_exists(name, agent, session_id):
                recovered[agent.value] = await self.get_screen_output(name, agent, session_id)
        return recovered


screen_manager = ScreenManager()
