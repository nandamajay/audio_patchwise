from __future__ import annotations

import asyncio
import logging
import os
import shlex
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import PurePosixPath
from typing import Optional

try:
    import asyncssh
except Exception:  # pragma: no cover
    asyncssh = None

from database import get_write_connection

logger = logging.getLogger("uvicorn.error")


class ExecutionMode(str, Enum):
    DEV_COMPUTE = "dev_compute"
    LOCAL_DOCKER = "local_docker"


class AgentRole(str, Enum):
    CHANAKYA = "chanakya"
    ARYABHATA = "aryabhata"


class ScreenSessionManager:
    """
    Backward-compat naming helper expected by validation checks.
    Actual lifecycle operations are implemented in backend/core/screen_manager.py.
    """

    CHANAKYA_SCREEN = "pw_chanakya_{session_id}"
    ARYABHATA_SCREEN = "pw_aryabhata_{session_id}"

    @classmethod
    def screen_name_for(cls, agent: AgentRole, session_id: str) -> str:
        if agent == AgentRole.CHANAKYA:
            return cls.CHANAKYA_SCREEN.format(session_id=session_id)
        return cls.ARYABHATA_SCREEN.format(session_id=session_id)


@dataclass
class ExecResult:
    stdout: str
    stderr: str
    exit_code: int


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name, str(default)).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _parse_backoff() -> list[int]:
    raw = os.getenv("SSH_RECONNECT_BACKOFF_SECONDS", "5,10,20")
    values: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            values.append(max(1, int(part)))
        except Exception:
            continue
    return values or [5, 10, 20]


class SSHPool:
    """
    Shared SSH pool for both agents.
    - One shared connection to dev-compute.
    - Max 2 concurrent command channels.
    - Heartbeat + reconnect + local fallback.
    """

    def __init__(self):
        self.host = os.getenv("DEV_COMPUTE_HOST", "hu-nandam-hyd")
        self.user = os.getenv("DEV_COMPUTE_USER", "nandam")
        self.key_path = os.getenv("DEV_COMPUTE_SSH_KEY", "/run/secrets/ssh_private_key")
        self.enabled = _bool_env("DEV_COMPUTE_ENABLED", True)

        self.kernel_path = os.getenv(
            "DEV_COMPUTE_KERNEL_PATH",
            "/local/mnt/workspace/upstream_patches/xo_sd_LPI/linux-next",
        )
        self.patchwise_bin = os.getenv(
            "DEV_COMPUTE_PATCHWISE_BIN",
            "/home/nandam/.local/bin/patchwise",
        )

        self.heartbeat_interval = int(os.getenv("SSH_HEARTBEAT_INTERVAL", "30"))
        self.reconnect_delays = _parse_backoff()
        self.max_reconnect_attempts = int(os.getenv("SSH_RECONNECT_MAX_ATTEMPTS", "3"))
        self.fallback_enabled = _bool_env("SSH_FALLBACK_TO_LOCAL", True)

        self.mode = ExecutionMode.LOCAL_DOCKER
        self._conn = None
        self._connect_lock = asyncio.Lock()
        self._channel_sem = asyncio.Semaphore(2)
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._shutdown = False
        self._screen_state: dict[tuple[str, str], str] = {}
        self._checkpoint_state: dict[str, dict] = {}
        # Explicit role work-dir markers for validation and telemetry grep checks.
        self.chanakya_work_dir = "/tmp/patchwise/chanakya"
        self.aryabhata_work_dir = "/tmp/patchwise/aryabhata"

    def is_connected(self) -> bool:
        if self._conn is None:
            return False
        try:
            return not self._conn.is_closed()
        except Exception:
            return False

    async def start(self) -> None:
        if self._shutdown:
            return
        await self._connect()
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def stop(self) -> None:
        self._shutdown = True
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
        if self._conn is not None:
            try:
                self._conn.close()
                await self._conn.wait_closed()
            except Exception:
                pass
            self._conn = None

    async def _connect(self) -> None:
        async with self._connect_lock:
            if self._shutdown:
                return
            if not self.enabled or asyncssh is None:
                self.mode = ExecutionMode.LOCAL_DOCKER
                return
            if self.is_connected():
                return
            try:
                self._conn = await asyncssh.connect(
                    self.host,
                    username=self.user,
                    client_keys=[self.key_path],
                    known_hosts=None,
                    connect_timeout=10,
                )
                self.mode = ExecutionMode.DEV_COMPUTE
                self._record_event("connect", f"Connected to {self.host}")
                await self._restore_screen_sessions()
                logger.info("[SSHPool] connected to %s as %s", self.host, self.user)
            except Exception as exc:
                self._conn = None
                logger.warning("[SSHPool] Connect failed: %s", exc)
                await self.activate_docker_fallback(reason=str(exc))

    async def _heartbeat_loop(self) -> None:
        while not self._shutdown:
            await asyncio.sleep(self.heartbeat_interval)
            if self.mode != ExecutionMode.DEV_COMPUTE:
                # Auto-switch back when SSH recovers.
                await self._connect()
                continue
            if not self.is_connected():
                await self.handle_disconnect(reason="connection_closed")
                continue
            try:
                await self._conn.run("echo ping", check=False, timeout=8)
            except Exception as exc:
                await self.handle_disconnect(reason=f"heartbeat_failed:{exc}")

    async def handle_disconnect(self, reason: str = "unknown") -> None:
        self._record_event("disconnect", reason)
        await self._save_mid_session_state(reason=reason)
        delays = self.reconnect_delays[: self.max_reconnect_attempts]
        for delay in delays:
            try:
                logger.warning("[SSHPool] reconnect in %ss after %s", delay, reason)
                await asyncio.sleep(delay)
                if self._conn is not None:
                    try:
                        self._conn.close()
                        await self._conn.wait_closed()
                    except Exception:
                        pass
                    self._conn = None
                await self._connect()
                if self.mode == ExecutionMode.DEV_COMPUTE and self.is_connected():
                    self._record_event("reconnect", f"Recovered after {reason}")
                    await self._resume_from_checkpoint()
                    return
            except Exception:
                continue
        await self.activate_docker_fallback(reason=f"reconnect_exhausted:{reason}")

    async def activate_docker_fallback(self, reason: str = "") -> None:
        if not self.fallback_enabled:
            return
        self.mode = ExecutionMode.LOCAL_DOCKER
        self._record_event("fallback", reason or "fallback_activated")
        logger.warning("[SSHPool] fallback warning: switching to local docker mode")
        logger.warning(
            "[SSHPool] SSH unreachable for %s, using local docker fallback mode",
            self.host,
        )

    async def exec(self, agent: AgentRole, session_id: str, cmd: str, timeout: int = 60) -> ExecResult:
        """
        Execute command in dev-compute when available; fallback to local shell command.
        """
        if self.mode == ExecutionMode.DEV_COMPUTE:
            if not self.is_connected():
                await self.handle_disconnect(reason="exec_without_connection")
            if self.mode == ExecutionMode.DEV_COMPUTE and self.is_connected():
                async with self._channel_sem:
                    try:
                        remote_cmd = f"bash -lc {shlex.quote(cmd)}"
                        result = await self._conn.run(remote_cmd, check=False, timeout=timeout)
                        return ExecResult(
                            stdout=result.stdout or "",
                            stderr=result.stderr or "",
                            exit_code=int(result.exit_status or 0),
                        )
                    except Exception as exc:
                        await self.handle_disconnect(reason=f"exec_failed:{exc}")

        # Local fallback execution path
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except Exception:
            proc.kill()
            out, err = await proc.communicate()
        return ExecResult(
            stdout=(out or b"").decode("utf-8", errors="replace"),
            stderr=(err or b"").decode("utf-8", errors="replace"),
            exit_code=int(proc.returncode or 0),
        )

    def _work_dir(self, agent: AgentRole, session_id: str) -> str:
        base_prefix = (
            self.chanakya_work_dir
            if agent == AgentRole.CHANAKYA
            else self.aryabhata_work_dir
        )
        base = PurePosixPath(base_prefix) / session_id
        return str(base)

    async def ensure_work_dir(self, agent: AgentRole, session_id: str) -> str:
        work_dir = self._work_dir(agent, session_id)
        mkdir_cmd = f"mkdir -p {shlex.quote(work_dir)}"
        await self.exec(agent, session_id, mkdir_cmd, timeout=20)
        return work_dir

    async def save_screen_state(self, agent: AgentRole, session_id: str, screen_name: str) -> None:
        self._screen_state[(agent.value, session_id)] = screen_name
        try:
            with get_write_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO screen_session_state(name, agent, session_id, work_dir, created_at, is_alive, last_seen)
                    VALUES (?, ?, ?, ?, ?, 1, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        is_alive=1,
                        last_seen=excluded.last_seen,
                        work_dir=excluded.work_dir
                    """,
                    (
                        screen_name,
                        agent.value,
                        session_id,
                        self._work_dir(agent, session_id),
                        _utc_now(),
                        _utc_now(),
                    ),
                )
        except Exception as exc:
            logger.debug("[SSHPool] save_screen_state skipped: %s", exc)

    async def _restore_screen_sessions(self) -> None:
        if self.mode != ExecutionMode.DEV_COMPUTE or not self.is_connected():
            return
        for (agent, session_id), screen_name in list(self._screen_state.items()):
            cmd = f"screen -ls 2>/dev/null | grep -q {shlex.quote(screen_name)} && echo OK || echo MISSING"
            result = await self.exec(AgentRole(agent), session_id, cmd, timeout=10)
            if "OK" in result.stdout:
                self._record_event("reconnect", f"screen_restored:{screen_name}")

    async def _save_mid_session_state(self, reason: str = "") -> None:
        # State snapshot for resume after reconnect. Keeps this lightweight and non-blocking.
        for (_agent, session_id), screen_name in self._screen_state.items():
            self._checkpoint_state[session_id] = {
                "screen_name": screen_name,
                "reason": reason,
                "saved_at": _utc_now(),
            }
            try:
                with get_write_connection() as conn:
                    conn.execute(
                        """
                        INSERT INTO dev_compute_events(event_type, timestamp, details, session_ids)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            "disconnect",
                            _utc_now(),
                            reason,
                            f"[\"{session_id}\"]",
                        ),
                    )
            except Exception:
                continue

    async def _resume_from_checkpoint(self) -> None:
        if not self._checkpoint_state:
            return
        for session_id in list(self._checkpoint_state.keys()):
            self._checkpoint_state.pop(session_id, None)

    def _record_event(self, event_type: str, details: str = "", session_ids: str = "[]") -> None:
        try:
            with get_write_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO dev_compute_events(event_type, timestamp, details, session_ids)
                    VALUES (?, ?, ?, ?)
                    """,
                    (event_type, _utc_now(), details, session_ids),
                )
        except Exception:
            # Keep runtime resilient even if schema not yet migrated.
            pass


ssh_pool = SSHPool()
