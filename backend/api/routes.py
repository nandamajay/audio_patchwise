from __future__ import annotations

import os

from fastapi import APIRouter

from app.config import settings
from knowledge_base.lkml_targeter import LKMLTargeter
from submission.dry_run import CheckStatus, DryRunManager

router = APIRouter(prefix="/api", tags=["advanced"])


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
