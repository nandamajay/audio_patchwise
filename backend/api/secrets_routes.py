from __future__ import annotations

import os
import subprocess

import httpx
from fastapi import APIRouter, HTTPException

from services.secrets_manager import secrets_manager

router = APIRouter(prefix="/api/secrets", tags=["secrets"])


@router.get("/validate")
async def validate_secrets():
    """Validate configured secrets for dashboard diagnostics."""
    return secrets_manager.validate_secrets()


@router.post("/rotate-github-token")
async def rotate_github_token(request: dict):
    """Hot-rotate GitHub token without restart."""
    new_token = request.get("token", "")
    if not new_token or len(new_token) < 10:
        raise HTTPException(status_code=400, detail="Invalid token")

    success = await secrets_manager.rotate_github_token(new_token)
    return {
        "success": success,
        "message": "Token rotated successfully" if success else "Rotation failed",
    }


@router.get("/test-gerrit-ssh")
async def test_gerrit_ssh():
    """Dry-run Gerrit SSH connectivity check."""
    gerrit_host = os.environ.get("GERRIT_HOST", "")
    gerrit_user = os.environ.get("GERRIT_USER", "")
    if not gerrit_host:
        return {"success": False, "message": "GERRIT_HOST not configured"}

    try:
        result = subprocess.run(
            [
                "ssh",
                "-T",
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "ConnectTimeout=5",
                f"{gerrit_user}@{gerrit_host}",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        success = "gerrit" in result.stderr.lower() or result.returncode == 0
        return {
            "success": success,
            "message": "Gerrit SSH connection successful" if success else f"Connection failed: {result.stderr}",
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "message": "Connection timed out"}
    except Exception as exc:
        return {"success": False, "message": str(exc)}


@router.get("/test-github-token")
async def test_github_token():
    """Test current GitHub token validity via GitHub API."""
    token = secrets_manager.get_github_token()
    if not token:
        return {"success": False, "message": "No GitHub token configured"}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.github.com/user",
                headers={"Authorization": f"token {token}"},
                timeout=10,
            )
            if response.status_code == 200:
                payload = response.json()
                return {
                    "success": True,
                    "message": f"GitHub token valid - logged in as {payload.get('login')}",
                    "username": payload.get("login"),
                    "scopes": response.headers.get("X-OAuth-Scopes", "unknown"),
                }
            return {"success": False, "message": f"Invalid token: HTTP {response.status_code}"}
    except Exception as exc:
        return {"success": False, "message": str(exc)}
