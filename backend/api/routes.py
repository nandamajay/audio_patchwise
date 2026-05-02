from __future__ import annotations

import os

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

from app.config import settings
from core.llm_factory import get_available_models
from core.patchwise_skill import PatchWiseSkill
from feedback.feedback_manager import FeedbackManager
from knowledge_base.lkml_targeter import LKMLTargeter
from monitoring.health_monitor import HealthMonitor
from submission.dry_run import CheckStatus, DryRunManager

router = APIRouter(prefix="/api", tags=["advanced"])


class KernelPathRequest(BaseModel):
    path: str


@router.post("/submission/dry-run")
async def run_dry_run(payload: dict):
    """Run preflight checks for selected submission target."""
    dry_run = DryRunManager()
    target = payload.get("target", "gerrit")
    config = payload.get("config", {})

    if target == "gerrit":
        checks = await dry_run.run_gerrit_preflight(config)
    elif target == "github":
        checks = await dry_run.run_github_preflight(config)
    elif target == "upstream":
        checks = await dry_run.run_upstream_preflight(config)
    else:
        checks = []

    return {
        "checks": [
            {
                "name": check.name,
                "description": check.description,
                "status": check.status.value,
                "message": check.message,
                "command_run": check.command_run,
            }
            for check in checks
        ],
        "all_pass": all(check.status in [CheckStatus.PASS, CheckStatus.WARN] for check in checks),
    }


@router.post("/submission/build-command")
async def build_command(payload: dict):
    """Return default submission command for optional user edit."""
    dry_run = DryRunManager()
    command = dry_run.build_submission_command(
        target=payload.get("target", "gerrit"),
        config=payload.get("config", {}),
    )
    return {"command": command}


@router.post("/submission/execute")
async def execute_submission(payload: dict):
    """Execute the possibly user-modified submission command."""
    dry_run = DryRunManager()
    result = await dry_run.execute_command(
        command=payload.get("command", ""),
        cwd=payload.get("cwd", "."),
    )
    return result


@router.post("/lkml/auto-detect")
async def auto_detect_targets(payload: dict):
    """Auto-detect mailing lists and maintainers from patch content."""
    kernel_path = os.getenv("KERNEL_PATH", getattr(settings, "KERNEL_PATH", "/workspace/linux"))
    targeter = LKMLTargeter(kernel_path=kernel_path)
    result = await targeter.auto_detect_from_patch(payload.get("patch_content", ""))
    return result


@router.get("/lkml/all-targets")
async def get_all_targets():
    """Return known mailing lists and maintainers for manual selection."""
    targeter = LKMLTargeter()
    return targeter.get_all_targets()


@router.post("/lkml/seed-targeted")
async def seed_targeted(payload: dict):
    """Trigger targeted LKML pre-seeding for selected mailing lists."""
    from knowledge_base.lkml_seeder import LKMLSeeder

    seeder = LKMLSeeder()
    result = await seeder.seed_specific_lists(
        list_ids=payload.get("list_ids", ["alsa-devel"]),
        months_back=payload.get("months_back", 24),
    )
    return result


@router.post("/feedback/vote")
async def record_vote(payload: dict):
    """Record upvote or downvote feedback for an agent message."""
    feedback_manager = FeedbackManager()
    result = await feedback_manager.record_feedback(
        session_id=payload["session_id"],
        round_num=payload["round_num"],
        agent=payload["agent"],
        message_id=payload["message_id"],
        message_content=payload["message_content"],
        vote=payload["vote"],
        comment=payload.get("comment"),
        issue_type=payload.get("issue_type"),
        subsystem=payload.get("subsystem", "audio"),
    )
    return result


@router.get("/feedback/leaderboard")
async def feedback_leaderboard():
    feedback_manager = FeedbackManager()
    return {"leaderboard": feedback_manager.get_leaderboard()}


@router.get("/health/full")
async def full_health():
    monitor = HealthMonitor()
    return monitor.get_full_health()


@router.post("/health/reseed")
async def trigger_reseed(background_tasks: BackgroundTasks):
    from knowledge_base.lkml_seeder import LKMLSeeder

    background_tasks.add_task(LKMLSeeder().seed_all)
    return {"message": "Re-seeding started in background"}


@router.post("/health/rebuild-embeddings")
async def rebuild_embeddings(background_tasks: BackgroundTasks):
    from knowledge_base.embedding_builder import rebuild_all

    background_tasks.add_task(rebuild_all)
    return {"message": "Embedding rebuild started in background"}


@router.get("/models")
async def get_models():
    """Returns available LLM models for UI dropdown — QGenie first."""
    return get_available_models()


@router.get("/patchwise/status")
async def get_patchwise_status():
    """PatchWise skill health check for System Health dashboard."""
    try:
        skill = PatchWiseSkill()
        return skill.get_status()
    except Exception as exc:
        return {"installed": False, "error": str(exc)}


@router.post("/validate-kernel-path")
async def validate_kernel_path(request: KernelPathRequest):
    path = request.path
    is_valid = (
        os.path.isdir(path)
        and os.path.exists(os.path.join(path, "scripts/checkpatch.pl"))
        and os.path.exists(os.path.join(path, "Makefile"))
    )
    return {
        "valid": is_valid,
        "has_checkpatch": os.path.exists(os.path.join(path, "scripts/checkpatch.pl")),
        "has_git": os.path.isdir(os.path.join(path, ".git")),
    }


@router.get("/debug/frontend-errors")
async def get_frontend_errors():
    """
    Lightweight debug endpoint for validation scripts.
    Frontend does not currently push Monaco error telemetry; return zero by default.
    """
    return {"monaco_errors": 0}
