from __future__ import annotations

from fastapi import APIRouter

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
