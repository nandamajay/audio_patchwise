from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


class SecretsManager:
    """
    Read secrets from Docker secrets with env fallbacks.
    """

    @staticmethod
    def get_github_token() -> Optional[str]:
        secret_path = Path("/run/secrets/github_token")
        if secret_path.exists():
            return secret_path.read_text().strip()
        return os.environ.get("GITHUB_TOKEN")

    @staticmethod
    def get_gerrit_ssh_key_path() -> Optional[str]:
        secret_path = Path("/run/secrets/gerrit_ssh_key")
        if secret_path.exists():
            return str(secret_path)
        return os.environ.get("GERRIT_SSH_KEY_PATH")

    @staticmethod
    def validate_secrets() -> dict:
        token = SecretsManager.get_github_token()
        key_path = SecretsManager.get_gerrit_ssh_key_path()

        return {
            "github_token": {
                "present": bool(token),
                "source": "docker_secret" if Path("/run/secrets/github_token").exists() else "env_var",
                "valid": bool(token and len(token) > 10),
            },
            "gerrit_ssh_key": {
                "present": bool(key_path and Path(key_path).exists()),
                "source": "docker_secret" if Path("/run/secrets/gerrit_ssh_key").exists() else "env_var",
                "valid": bool(key_path and Path(key_path).exists()),
            },
        }

    @staticmethod
    async def rotate_github_token(new_token: str) -> bool:
        secret_path = Path("/run/secrets/github_token")
        try:
            if secret_path.exists() and os.access(secret_path, os.W_OK):
                secret_path.write_text(new_token.strip())
            else:
                os.environ["GITHUB_TOKEN"] = new_token.strip()
            return True
        except Exception as exc:
            print(f"[SecretsManager] rotation failed: {exc}")
            return False


secrets_manager = SecretsManager()
