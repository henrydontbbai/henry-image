from __future__ import annotations

import os


CANONICAL_API_KEY_ENV = "HENRY_IMAGE_API_KEY"


def env_get(name: str) -> str | None:
    return os.environ.get(name)


def resolve_api_key(api_key_env: str | None = None) -> tuple[str | None, str | None]:
    env_names = [api_key_env] if api_key_env else [CANONICAL_API_KEY_ENV]
    for name in env_names:
        if not name:
            continue
        value = env_get(name)
        if value:
            return value, name
    return None, None


def bearer_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}
