#!/usr/bin/env python3
"""Henry image helper for mixed Codex/API image generation environments."""

from __future__ import annotations

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import mimetypes
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import socket
import tomllib
from typing import Any
from urllib import error, parse, request
import uuid

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from henry_image_core.cli import clone_args
from henry_image_core.contracts import ApiResult, AuthProfile, ImageTask
from henry_image_core import auth as core_auth
from henry_image_core import jobs as core_jobs
from henry_image_core import prompts as core_prompts
from henry_image_core import providers as core_providers
from henry_image_core import request as core_request
from henry_image_core import routing as core_routing
from henry_image_core import validate as core_validate
from henry_image_core.workflow import attach_workflow_metadata


HENRY_IMAGE_VERSION = "0.1.6"
HENRY_IMAGE_DISPLAY_NAME = f"Henry Image V{HENRY_IMAGE_VERSION}"
DEFAULT_MODEL = "gpt-5"
DEFAULT_IMAGE_MODEL = "gpt-image-2"
DEFAULT_SIZE = "1024x1024"
DEFAULT_QUALITY = "medium"
DEFAULT_OUTPUT_FORMAT = "png"
DEFAULT_OUT = "output/imagegen/henry-image.png"
DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_TIMEOUT = 600
DEFAULT_JOBS_DIR = "output/imagegen/jobs"
DEFAULT_AZURE_API_VERSION = "2024-10-21"
FINAL_JOB_STATUSES = {"completed", "failed", "cancelled"}
CANDIDATE_POLICIES = {"all", "auto", "strict"}
MAX_BATCH_CONCURRENCY = 12
MAX_IMAGE_BYTES = 50 * 1024 * 1024
SKILL_ROOT = Path(__file__).resolve().parent.parent
SKILL_CACHE_ROOT = SKILL_ROOT / ".cache"
DEFAULT_IMAGE_PROVIDER_HEALTH_CACHE = SKILL_CACHE_ROOT / "image-provider-health.json"
IMAGE_PROVIDER_SHORT_COOLDOWN_SECONDS = 30 * 60
IMAGE_PROVIDER_MEDIUM_COOLDOWN_SECONDS = 6 * 60 * 60
IMAGE_PROVIDER_LONG_COOLDOWN_SECONDS = 24 * 60 * 60
IMAGE_PROVIDER_UNUSABLE_COOLDOWN_SECONDS = IMAGE_PROVIDER_MEDIUM_COOLDOWN_SECONDS
IMAGE_PROVIDER_SUCCESS_TTL_SECONDS = 7 * 24 * 60 * 60
IMAGE_PROVIDER_STATUS_COOLDOWNS = {
    "responses_upstream_502": IMAGE_PROVIDER_SHORT_COOLDOWN_SECONDS,
    "responses_server_error": IMAGE_PROVIDER_SHORT_COOLDOWN_SECONDS,
    "timeout": IMAGE_PROVIDER_SHORT_COOLDOWN_SECONDS,
    "network_error": IMAGE_PROVIDER_SHORT_COOLDOWN_SECONDS,
    "responses_unsupported": IMAGE_PROVIDER_MEDIUM_COOLDOWN_SECONDS,
    "images_unsupported": IMAGE_PROVIDER_MEDIUM_COOLDOWN_SECONDS,
    "image_generation_disabled": IMAGE_PROVIDER_LONG_COOLDOWN_SECONDS,
}
DEFAULT_CODEX_CONFIG = Path.home() / ".codex" / "config.toml"
DEFAULT_CODEX_AUTH = Path.home() / ".codex" / "auth.json"
DEFAULT_AIMAMI_STATE = Path.home() / ".codex" / "codexmate" / "relay" / "state.json"
DEDICATED_API_KEY_ENV_NAMES = (
    "HENRY_IMAGE_API_KEY",
    "HENRY_IMAGE_OPENAI_API_KEY",
    "HENRY_IMAGE_ACCESS_KEY",
)
DEFAULT_API_KEY_ENV_NAMES = (
    "HENRY_IMAGE_API_KEY",
    "HENRY_IMAGE_OPENAI_API_KEY",
    "HENRY_IMAGE_ACCESS_KEY",
    "OPENAI_API_KEY",
    "OPENAI_IMAGE_API_KEY",
    "IMAGES_OPENAI_API_KEY",
    "IMAGE_OPENAI_API_KEY",
    "OPENAI_COMPAT_API_KEY",
    "CODEX_OPENAI_API_KEY",
    "AIMAMI_API_KEY",
    "AIMA_API_KEY",
    "GPT_IMAGE_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "AOAI_API_KEY",
)
API_KEY_ENV_NAME_PATTERNS = (
    re.compile(r"^(OPENAI|HENRY|AIMAMI|AIMA|CODEX|GPT|IMAGE).*(API|ACCESS).*KEY$", re.IGNORECASE),
    re.compile(r"^.*(OPENAI|IMAGE).*KEY$", re.IGNORECASE),
)
DEDICATED_BASE_URL_ENV_NAMES = (
    "HENRY_IMAGE_BASE_URL",
    "HENRY_IMAGE_API_BASE",
    "HENRY_IMAGE_API_BASE_URL",
)
DEFAULT_BASE_URL_ENV_NAMES = (
    "HENRY_IMAGE_BASE_URL",
    "HENRY_IMAGE_API_BASE",
    "HENRY_IMAGE_API_BASE_URL",
    "OPENAI_BASE_URL",
    "OPENAI_API_BASE",
    "OPENAI_API_BASE_URL",
    "IMAGES_OPENAI_API_BASE_URL",
    "IMAGES_OPENAI_BASE_URL",
    "IMAGE_OPENAI_API_BASE_URL",
    "OPENAI_COMPAT_BASE_URL",
    "OPENAI_COMPAT_API_BASE",
    "AIMAMI_BASE_URL",
    "AIMAMI_API_BASE",
    "AIMAMI_API_BASE_URL",
    "AIMA_BASE_URL",
    "GPT_IMAGE_BASE_URL",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_BASE_URL",
    "AOAI_API_BASE",
    "AOAI_ENDPOINT",
)
BASE_URL_ENV_NAME_PATTERNS = (
    re.compile(r"^(OPENAI|HENRY|AIMAMI|AIMA|CODEX|GPT|IMAGE).*(BASE|API).*URL$", re.IGNORECASE),
    re.compile(r"^(OPENAI|HENRY|AIMAMI|AIMA|CODEX|GPT|IMAGE).*API_BASE$", re.IGNORECASE),
)
DEFAULT_MODEL_ENV_NAMES = ("HENRY_IMAGE_MODEL", "HENRY_IMAGE_RESPONSE_MODEL", "OPENAI_MODEL")
DEFAULT_IMAGE_MODEL_ENV_NAMES = ("HENRY_IMAGE_IMAGE_MODEL", "HENRY_IMAGE_MODEL_IMAGE", "OPENAI_IMAGE_MODEL")
OPENAI_ORG_ENV_NAMES = ("OPENAI_ORG_ID", "OPENAI_ORGANIZATION", "OPENAI_ORGANIZATION_ID")
OPENAI_PROJECT_ENV_NAMES = ("OPENAI_PROJECT", "OPENAI_PROJECT_ID")
AZURE_API_VERSION_ENV_NAMES = (
    "AZURE_OPENAI_API_VERSION",
    "AOAI_API_VERSION",
    "OPENAI_API_VERSION",
    "HENRY_IMAGE_AZURE_API_VERSION",
)

QUALITIES = {"low", "medium", "high", "auto", "standard", "hd"}
OUTPUT_FORMATS = {"png", "jpeg", "webp"}
IMAGES_RESPONSE_FORMATS = {"auto", "b64_json", "url"}
IMAGES_COMPAT_MODES = {"auto", "openai", "minimal"}
INPUT_FIDELITIES = {"auto", "high", "low"}
BACKGROUNDS = {"auto", "opaque", "transparent"}
MODERATIONS = {"auto", "low"}
ROUTES = {"auto", "responses", "images"}
PROMPT_PACKAGE_VERSIONS = {"1", "2"}
PROMPT_PLATFORMS = {"all", "openai", "flux", "sdxl", "midjourney"}
REVIEW_TEMPLATES = {"auto", "photo", "product", "social", "engineering"}
RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}
SECRET_PATTERNS = [
    re.compile(r"sk-[^\s\"'<>]+"),
    re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]+", re.IGNORECASE),
    re.compile(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"),
]
BASE_ENDPOINT_SUFFIXES = (
    "/chat/completions",
    "/responses",
    "/images/generations",
    "/images/edits",
    "/images/variations",
)


def sensitive_dict_key(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    normalized = key.strip().lower().replace("-", "_").replace(" ", "_")
    return normalized in {
        "authorization",
        "api_key",
        "x_api_key",
        "openai_organization",
        "openai_project",
        "access_token",
        "refresh_token",
        "id_token",
        "token",
        "client_secret",
        "secret",
        "custom_token",
    }


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stderr_event(event: str, **fields: Any) -> None:
    text = json.dumps(redact({"event": event, **fields}), ensure_ascii=False)
    try:
        print(text, file=sys.stderr)
    except UnicodeEncodeError:
        sys.stderr.buffer.write((text + "\n").encode("utf-8", errors="replace"))


def windows_user_env(name: str) -> str | None:
    if os.name != "nt" or not name:
        return None
    if os.environ.get("HENRY_IMAGE_DISABLE_WINDOWS_USER_ENV"):
        return None
    try:
        import winreg  # type: ignore[import-not-found]

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, name)
    except Exception:  # noqa: BLE001
        return None
    return value if isinstance(value, str) and value else None


def env_get(name: str) -> str | None:
    return os.environ.get(name) or windows_user_env(name)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: (
                "[REDACTED_SECRET]"
                if sensitive_dict_key(k) and isinstance(v, str) and v
                else redact(v)
            )
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(v) for v in value]
    if not isinstance(value, str):
        return value
    redacted = value
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED_SECRET]", redacted)
    redacted = re.sub(
        r'(?i)("?(?:authorization|api-key|x-api-key|openai-organization|openai-project|codex(?:[-_ ]?(?:access[-_ ]?)?token)?)"?\s*:\s*")([^"]{6,})(")',
        lambda match: f"{match.group(1)}[REDACTED_SECRET]{match.group(3)}",
        redacted,
    )
    redacted = re.sub(
        r"(?i)\b(api-key|x-api-key|openai-organization|openai-project|codex(?:[-_ ]?(?:access[-_ ]?)?token)?)\b(\s*[:=]\s*)([A-Za-z0-9._~:/+=-]{6,})",
        lambda match: f"{match.group(1)}{match.group(2)}[REDACTED_SECRET]",
        redacted,
    )
    try:
        for secret in known_secret_values():
            if secret:
                redacted = redacted.replace(secret, "[REDACTED_SECRET]")
    except Exception:  # noqa: BLE001
        pass
    redacted = re.sub(
        r"data:image/[a-zA-Z0-9.+-]+;base64,[A-Za-z0-9+/=]+",
        "data:image/...;base64,[REDACTED_IMAGE_DATA]",
        redacted,
    )
    return redacted


def envelope(
    *,
    ok: bool,
    command: str,
    status: str,
    provider: dict[str, Any],
    outputs: list[dict[str, Any]] | None = None,
    error_obj: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "status": status,
        "command": command,
        "provider": redact(provider),
        "request_id": request_id,
        "outputs": redact(outputs or []),
        "error": redact(error_obj),
        "metadata": redact(metadata or {}),
    }


def emit(payload: dict[str, Any]) -> int:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    try:
        print(text)
    except UnicodeEncodeError:
        sys.stdout.buffer.write((text + "\n").encode("utf-8", errors="replace"))
    return 0 if payload.get("ok") else 1


def emit_with_workflow(
    payload: dict[str, Any],
    *,
    args: argparse.Namespace,
    command: str,
    out: str,
    source_output: str | None = None,
    persist_on_success: bool = True,
) -> int:
    attach_workflow_metadata(
        payload,
        cache_root=SKILL_CACHE_ROOT,
        args=args,
        command=command,
        out=out,
        source_output=source_output,
        persist_on_success=persist_on_success,
    )
    return emit(payload)


def read_prompt(prompt: str | None, prompt_file: str | None) -> str:
    return core_validate.read_prompt(prompt, prompt_file)


def normalize_base_url(base_url: str | None) -> str:
    value = base_url
    if not value:
        dedicated_value, _ = env_value(DEDICATED_BASE_URL_ENV_NAMES)
        if dedicated_value:
            value = dedicated_value
        else:
            for env_name in DEFAULT_BASE_URL_ENV_NAMES:
                raw_env_value = env_get(env_name)
                if raw_env_value:
                    value = raw_env_value
                    break
    value = (value or DEFAULT_BASE_URL).strip()
    value = value.rstrip("/")
    for suffix in BASE_ENDPOINT_SUFFIXES:
        if value.endswith(suffix):
            value = value[: -len(suffix)].rstrip("/")
            break
    return value


def env_value(names: tuple[str, ...]) -> tuple[str | None, str | None]:
    for name in names:
        value = env_get(name)
        if value:
            return value, name
    return None, None


def dedicated_base_url_candidate() -> tuple[str, str] | None:
    value, env_name = env_value(DEDICATED_BASE_URL_ENV_NAMES)
    if value:
        return normalize_base_url(value), env_name or "HENRY_IMAGE_BASE_URL"
    return None


def endpoint(base_url: str, path: str) -> str:
    if base_url.endswith(path):
        return base_url
    return f"{base_url}{path}"


def provider_info(base_url: str, route: str = "responses") -> dict[str, Any]:
    parsed = parse.urlparse(base_url)
    provider_type = {
        "auto": "henry-auto-image-router",
        "responses": "henry-responses-image-generation",
        "images": "henry-images-api-generation",
    }.get(route, "henry-image-router")
    return {
        "type": provider_type,
        "route": route,
        "base_url_host": parsed.netloc or base_url,
        "responses_endpoint": endpoint(base_url, "/responses"),
        "images_endpoint": endpoint(base_url, "/images/generations"),
        "images_edits_endpoint": endpoint(base_url, "/images/edits"),
    }


def configured_model(cli_value: str, default_value: str, env_names: tuple[str, ...]) -> tuple[str, str]:
    if cli_value != default_value:
        return cli_value, "cli"
    value, env_name = env_value(env_names)
    if value:
        return value, env_name or "env"
    return default_value, "default"


def apply_model_env_defaults(args: argparse.Namespace) -> None:
    args.model, args.model_source = configured_model(args.model, DEFAULT_MODEL, DEFAULT_MODEL_ENV_NAMES)
    args.image_model, args.image_model_source = configured_model(
        args.image_model,
        DEFAULT_IMAGE_MODEL,
        DEFAULT_IMAGE_MODEL_ENV_NAMES,
    )


def api_key_env_candidates(preferred: str | None) -> list[str]:
    names: list[str] = []
    for raw in (preferred or "").split(","):
        name = raw.strip()
        if name:
            names.append(name)
    names.extend(DEFAULT_API_KEY_ENV_NAMES)
    for name in sorted(os.environ):
        if any(pattern.fullmatch(name) for pattern in API_KEY_ENV_NAME_PATTERNS):
            names.append(name)
    deduped: list[str] = []
    for name in names:
        if name and name not in deduped:
            deduped.append(name)
    return deduped


def api_key_candidates(preferred_env: str | None = None) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    seen_values: set[str] = set()
    for name in api_key_env_candidates(preferred_env):
        value = env_get(name)
        if not value:
            continue
        if value in seen_values:
            continue
        candidates.append((value, name))
        seen_values.add(value)
    return candidates


def get_api_key(preferred_env: str | None = None) -> tuple[str | None, str | None]:
    candidates = api_key_candidates(preferred_env)
    if candidates:
        return candidates[0]
    return None, None


def should_try_next_api_key(result: ApiResult) -> bool:
    error_data = result.error or {}
    status = error_data.get("status")
    code = str(error_data.get("code") or "").lower()
    message = str(error_data.get("message") or "").lower()
    category = classify_api_failure(error_data)
    if category in {"content_policy", "quota_exceeded", "rate_limited", "bad_parameter"}:
        return False
    return (
        category in {"invalid_credentials", "missing_credentials"}
        or status in {401, 403}
        or code in {"invalid_api_key", "missing_openai_api_key"}
        or "incorrect api key" in message
    )


def resolve_base_url(base_url: str | None) -> tuple[str, str]:
    if base_url:
        return normalize_base_url(base_url), "cli"
    dedicated = dedicated_base_url_candidate()
    if dedicated:
        return dedicated
    value, env_name = env_value(DEFAULT_BASE_URL_ENV_NAMES)
    if value:
        return normalize_base_url(value), env_name or "env"
    return DEFAULT_BASE_URL, "default"


def codex_config_path() -> Path:
    return Path(os.getenv("HENRY_IMAGE_CODEX_CONFIG") or os.getenv("CODEX_CONFIG") or DEFAULT_CODEX_CONFIG)


def codex_auth_path() -> Path:
    return Path(os.getenv("HENRY_IMAGE_CODEX_AUTH") or os.getenv("CODEX_AUTH") or DEFAULT_CODEX_AUTH)


def aimami_state_path() -> Path:
    return Path(os.getenv("HENRY_IMAGE_AIMAMI_STATE") or DEFAULT_AIMAMI_STATE)


def image_provider_health_cache_path() -> Path:
    return Path(os.getenv("HENRY_IMAGE_PROVIDER_HEALTH_CACHE") or DEFAULT_IMAGE_PROVIDER_HEALTH_CACHE)


def read_json_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001
        return None
    return data if isinstance(data, dict) else None


def codex_config_data() -> dict[str, Any] | None:
    path = codex_config_path()
    if not path.exists():
        return None
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    return data if isinstance(data, dict) else None


def aimami_state_data() -> dict[str, Any] | None:
    return read_json_file(aimami_state_path())


def image_provider_health_cache() -> dict[str, Any]:
    data = read_json_file(image_provider_health_cache_path())
    if not isinstance(data, dict):
        return {"version": 1, "providers": {}}
    providers = data.get("providers")
    if not isinstance(providers, dict):
        data["providers"] = {}
    return data


def write_image_provider_health_cache(data: dict[str, Any]) -> None:
    path = image_provider_health_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def codex_model_catalog_path() -> Path | None:
    data = codex_config_data()
    if not isinstance(data, dict):
        return None
    value = data.get("model_catalog_json")
    return Path(value) if isinstance(value, str) and value else None


def extract_actual_model(description: str | None) -> str | None:
    if not isinstance(description, str) or not description:
        return None
    match = re.search(r"实际模型\s*([A-Za-z0-9._:-]+)", description)
    if match:
        return match.group(1)
    match = re.search(r"actual\s+model\s*[:：]?\s*([A-Za-z0-9._:-]+)", description, re.IGNORECASE)
    return match.group(1) if match else None


def codex_catalog_model_info(model_slug: str | None) -> dict[str, Any] | None:
    path = codex_model_catalog_path()
    if not path or not path.exists() or not isinstance(model_slug, str) or not model_slug:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    models = data.get("models") if isinstance(data, dict) else None
    if not isinstance(models, list):
        return None
    for item in models:
        if not isinstance(item, dict):
            continue
        if item.get("slug") != model_slug:
            continue
        description = item.get("description")
        return {
            "slug": item.get("slug"),
            "display_name": item.get("display_name"),
            "description": description,
            "actual_model": extract_actual_model(description),
        }
    return None


def codex_catalog_model_actual(model_slug: str | None) -> str | None:
    catalog_info = codex_catalog_model_info(model_slug)
    actual_model = catalog_info.get("actual_model") if isinstance(catalog_info, dict) else None
    return actual_model if isinstance(actual_model, str) and actual_model else None


def codex_provider_by_name(provider_name: str | None) -> dict[str, Any] | None:
    data = codex_config_data()
    if not isinstance(data, dict):
        return None
    providers = data.get("model_providers") if isinstance(data.get("model_providers"), dict) else {}
    provider = providers.get(provider_name) if isinstance(provider_name, str) else None
    return provider if isinstance(provider, dict) else None


def codex_profile_by_name(profile_name: str | None) -> dict[str, Any] | None:
    data = codex_config_data()
    if not isinstance(data, dict):
        return None
    profiles = data.get("profiles") if isinstance(data.get("profiles"), dict) else {}
    profile = profiles.get(profile_name) if isinstance(profile_name, str) else None
    return profile if isinstance(profile, dict) else None


def codex_active_provider() -> dict[str, Any] | None:
    data = codex_config_data()
    if not isinstance(data, dict):
        return None
    model_provider = data.get("model_provider")
    return codex_provider_by_name(model_provider if isinstance(model_provider, str) else None)


def safe_codex_provider(provider: dict[str, Any]) -> dict[str, Any]:
    base_url = provider.get("base_url")
    return {
        "name": provider.get("name"),
        "base_url": normalize_base_url(base_url) if isinstance(base_url, str) and base_url else None,
        "wire_api": provider.get("wire_api"),
        "requires_openai_auth": provider.get("requires_openai_auth"),
        "supports_websockets": provider.get("supports_websockets"),
        "env_key": provider.get("env_key") if isinstance(provider.get("env_key"), str) else None,
        "api_key": "set" if provider.get("api_key") else "missing",
    }


def codex_access_token() -> tuple[str | None, str]:
    path = codex_auth_path()
    if not path.exists():
        return None, "missing"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None, "unreadable"
    tokens = data.get("tokens") if isinstance(data, dict) else None
    access_token = tokens.get("access_token") if isinstance(tokens, dict) else None
    if isinstance(access_token, str) and access_token:
        return access_token, "set"
    return None, "missing"


def codex_access_info() -> dict[str, Any]:
    path = codex_config_path()
    info: dict[str, Any] = {
        "mode": "codex_config_missing",
        "config_path": str(path),
        "model_provider": None,
        "model": None,
        "provider": None,
    }
    if not path.exists():
        return info
    data = codex_config_data()
    if data is None:
        info["mode"] = "codex_config_unreadable"
        return info

    model_provider = data.get("model_provider")
    model = data.get("model")
    providers = data.get("model_providers") if isinstance(data.get("model_providers"), dict) else {}
    provider = providers.get(model_provider) if isinstance(model_provider, str) else None
    info["model_provider"] = model_provider
    info["model"] = model
    if not isinstance(provider, dict):
        info["mode"] = "codex_provider_missing"
        return info

    safe_provider = safe_codex_provider(provider)
    info["provider"] = safe_provider
    catalog_path = codex_model_catalog_path()
    if catalog_path:
        info["model_catalog_path"] = str(catalog_path)
    catalog_info = codex_catalog_model_info(model if isinstance(model, str) else None)
    if catalog_info:
        info["model_catalog_entry"] = catalog_info
    model_provider_candidate = codex_provider_by_name(model if isinstance(model, str) else None)
    if isinstance(model_provider_candidate, dict) and model != model_provider:
        info["model_provider_candidate"] = safe_codex_provider(model_provider_candidate)
    info["mode"] = "codex_model_provider" if safe_provider["base_url"] else "codex_provider_without_base_url"
    token, token_status = codex_access_token()
    info["codex_auth"] = {
        "path": str(codex_auth_path()),
        "access_token": "set" if token else token_status,
    }
    return info


def effective_codex_access_info() -> dict[str, Any]:
    dedicated = dedicated_base_url_candidate()
    if dedicated:
        return {
            "mode": "dedicated_henry_image_provider",
            "codex_read": False,
            "base_url_source": dedicated[1],
        }
    return codex_access_info()


def codex_provider_model(provider_name: str | None) -> str | None:
    profile = codex_profile_by_name(provider_name)
    if isinstance(profile, dict):
        value = profile.get("model")
        if isinstance(value, str) and value:
            return value
    provider = codex_provider_by_name(provider_name)
    if isinstance(provider, dict):
        for field in ("model", "actual_model"):
            value = provider.get(field)
            if isinstance(value, str) and value:
                return value
    actual_model = codex_catalog_model_actual(provider_name)
    if actual_model:
        return actual_model
    return None


def codex_base_url_candidate() -> tuple[str, str] | None:
    access = codex_access_info()
    provider = access.get("provider")
    if not isinstance(provider, dict):
        return None
    base_url = provider.get("base_url")
    provider_name = access.get("model_provider")
    if isinstance(base_url, str) and base_url and isinstance(provider_name, str) and provider_name:
        return normalize_base_url(base_url), f"codex_config:{provider_name}"
    return None


def codex_provider_name_from_source(base_url_source: str | None) -> str | None:
    if not base_url_source or not base_url_source.startswith("codex_config:"):
        return None
    provider_name = base_url_source.split(":", 1)[1].strip()
    return provider_name or None


def image_provider_id_from_source(base_url_source: str | None) -> str | None:
    if not base_url_source:
        return None
    for prefix in ("codex_config:", "aimami_state:"):
        if base_url_source.startswith(prefix):
            value = base_url_source.split(":", 1)[1].strip()
            return value or None
    return None


def aimami_state_provider_by_id(provider_id: str | None) -> dict[str, Any] | None:
    data = aimami_state_data()
    providers = data.get("providers") if isinstance(data, dict) else None
    if not isinstance(providers, list) or not isinstance(provider_id, str):
        return None
    for item in providers:
        if isinstance(item, dict) and item.get("id") == provider_id:
            return item
    return None


def aimami_state_proxy_base_url() -> str | None:
    data = aimami_state_data()
    proxy = data.get("proxy") if isinstance(data, dict) else None
    base_url = proxy.get("baseUrl") if isinstance(proxy, dict) else None
    return normalize_base_url(base_url) if isinstance(base_url, str) and base_url else None


def aimami_state_provider_base_url(provider_id: str) -> str | None:
    proxy_base_url = aimami_state_proxy_base_url()
    if not proxy_base_url:
        return None
    return normalize_base_url(f"{proxy_base_url}/codex/by-provider/{provider_id}/v1")


def codex_provider_from_source(base_url_source: str | None) -> dict[str, Any] | None:
    provider_name = codex_provider_name_from_source(base_url_source)
    return codex_provider_by_name(provider_name)


def codex_provider_requires_auth(base_url_source: str | None) -> bool | None:
    provider = codex_provider_from_source(base_url_source)
    if not isinstance(provider, dict):
        return None
    value = provider.get("requires_openai_auth")
    return value if isinstance(value, bool) else None


def codex_configured_model(base_url_source: str | None) -> str | None:
    provider_name = image_provider_id_from_source(base_url_source)
    if not provider_name:
        return None
    if base_url_source and base_url_source.startswith("aimami_state:"):
        provider = aimami_state_provider_by_id(provider_name)
        model = provider.get("model") if isinstance(provider, dict) else None
        return model if isinstance(model, str) and model else None
    provider_model = codex_provider_model(provider_name)
    if provider_model:
        return provider_model
    model = codex_access_info().get("model")
    return model if isinstance(model, str) and model else None


def codex_responses_model(base_url_source: str | None) -> tuple[str | None, str | None]:
    model = codex_configured_model(base_url_source)
    if not model:
        return None, None
    if base_url_source and base_url_source.startswith("aimami_state:"):
        return model, "aimami_state"
    source_provider = codex_provider_name_from_source(base_url_source)
    if source_provider == model:
        actual_model = codex_catalog_model_actual(model)
        if actual_model:
            return actual_model, "codex_catalog"
    return model, "codex_config"


def codex_provider_records() -> list[dict[str, Any]]:
    data = codex_config_data()
    providers = data.get("model_providers") if isinstance(data, dict) and isinstance(data.get("model_providers"), dict) else {}
    records: list[dict[str, Any]] = []
    for name, provider in providers.items():
        if not isinstance(name, str) or not name or not isinstance(provider, dict):
            continue
        base_url = provider.get("base_url")
        if not isinstance(base_url, str) or not base_url:
            continue
        records.append({"name": name, "provider": provider, "base_url": normalize_base_url(base_url)})
    return records


def codex_provider_display_model(provider: dict[str, Any], name: str | None = None) -> str | None:
    profile_model = codex_provider_model(name)
    if profile_model:
        return profile_model
    for field in ("model", "actual_model"):
        value = provider.get(field)
        if isinstance(value, str) and value:
            return value
    if isinstance(name, str) and name:
        model = codex_catalog_model_actual(name)
        if model:
            return model
    return None


def provider_identity_from_base_url(base_url: str) -> str | None:
    prefix = "/codex/by-provider/"
    parsed = parse.urlparse(base_url)
    path = parsed.path.rstrip("/")
    if prefix not in path:
        return None
    try:
        tail = path.split(prefix, 1)[1]
        provider_name = tail.split("/", 1)[0].strip()
    except Exception:  # noqa: BLE001
        return None
    return provider_name or None


def parse_iso_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def seconds_since_iso(value: Any) -> float | None:
    parsed = parse_iso_time(value)
    if parsed is None:
        return None
    return (datetime.now(timezone.utc) - parsed).total_seconds()


def image_provider_cache_entry(provider_id: str | None) -> dict[str, Any]:
    if not provider_id:
        return {}
    cache = image_provider_health_cache()
    providers = cache.get("providers") if isinstance(cache.get("providers"), dict) else {}
    entry = providers.get(provider_id)
    return entry if isinstance(entry, dict) else {}


def image_provider_cache_unusable(entry: dict[str, Any]) -> bool:
    status = str(entry.get("status") or "")
    if status == "verified":
        return False
    cooldown = IMAGE_PROVIDER_STATUS_COOLDOWNS.get(status)
    if cooldown is None:
        return False
    age = seconds_since_iso(entry.get("last_error_at"))
    return age is not None and age < cooldown


def image_provider_cache_cooldown_info(entry: dict[str, Any]) -> dict[str, Any]:
    status = str(entry.get("status") or "")
    cooldown = IMAGE_PROVIDER_STATUS_COOLDOWNS.get(status)
    age = seconds_since_iso(entry.get("last_error_at"))
    remaining: float | None = None
    if cooldown is not None and age is not None:
        remaining = max(float(cooldown) - age, 0.0)
    return {
        "status": status,
        "cooldown_seconds": cooldown,
        "age_seconds": age,
        "remaining_seconds": remaining,
        "unusable": bool(cooldown is not None and age is not None and age < cooldown),
    }


def format_duration(seconds: Any) -> str:
    if seconds is None:
        return "未知"
    try:
        total = max(int(float(seconds)), 0)
    except (TypeError, ValueError):
        return "未知"
    if total < 60:
        return f"{total}秒"
    minutes = total // 60
    if minutes < 60:
        return f"{minutes}分钟"
    hours = minutes // 60
    rest_minutes = minutes % 60
    if hours < 24:
        return f"{hours}小时{rest_minutes}分钟" if rest_minutes else f"{hours}小时"
    days = hours // 24
    rest_hours = hours % 24
    return f"{days}天{rest_hours}小时" if rest_hours else f"{days}天"


def image_provider_cache_entries() -> list[dict[str, Any]]:
    cache = image_provider_health_cache()
    providers = cache.get("providers") if isinstance(cache.get("providers"), dict) else {}
    entries: list[dict[str, Any]] = []
    for provider_id, entry in providers.items():
        if not isinstance(entry, dict):
            continue
        item = dict(entry)
        item.setdefault("provider_id", provider_id)
        item["cooldown"] = image_provider_cache_cooldown_info(item)
        item["image_generation_capability"] = image_generation_capability_from_cache(item)
        entries.append(item)

    def sort_key(item: dict[str, Any]) -> tuple[int, str]:
        status = str(item.get("status") or "")
        if status == "verified":
            rank = 0
        elif (item.get("cooldown") or {}).get("unusable"):
            rank = 1
        else:
            rank = 2
        return (rank, str(item.get("provider_id") or ""))

    return sorted(entries, key=sort_key)


def clear_image_provider_health_cache(provider_id: str | None = None) -> dict[str, Any]:
    cache = image_provider_health_cache()
    providers = cache.get("providers") if isinstance(cache.get("providers"), dict) else {}
    if provider_id:
        removed = providers.pop(provider_id, None)
        cache["providers"] = providers
        write_image_provider_health_cache(cache)
        return {
            "provider_id": provider_id,
            "removed": bool(isinstance(removed, dict)),
            "remaining_count": len(providers),
            "cache_path": str(image_provider_health_cache_path()),
        }
    removed_count = len(providers)
    cache = {"version": 1, "providers": {}}
    write_image_provider_health_cache(cache)
    return {
        "provider_id": None,
        "removed_count": removed_count,
        "remaining_count": 0,
        "cache_path": str(image_provider_health_cache_path()),
    }


def image_provider_cache_reason(entry: dict[str, Any]) -> str:
    status = str(entry.get("status") or "unknown")
    message = str((entry.get("last_error") or {}).get("message") or "").strip()
    if status == "image_generation_disabled":
        return "provider recently rejected image_generation tool calls"
    if status == "responses_upstream_502":
        return "provider recently returned Responses upstream 502"
    if status == "images_unsupported":
        return "provider recently returned Images route 404/unsupported"
    if status in {"responses_server_error", "responses_unsupported", "timeout", "network_error"}:
        return f"provider recently failed with {status}" + (f": {message}" if message else "")
    return "provider recently marked unavailable"


def image_provider_cache_reason_zh(entry: dict[str, Any]) -> str:
    status = str(entry.get("status") or "unknown")
    message = str((entry.get("last_error") or {}).get("message") or "").strip()
    if status == "verified":
        return "最近真实生图成功"
    if status == "image_generation_disabled":
        return "上游明确没有开启图片生成能力"
    if status == "responses_upstream_502":
        return "Responses 上游 502"
    if status == "responses_server_error":
        return "Responses 上游服务错误"
    if status == "responses_unsupported":
        return "Responses 返回成功但没有图片字节"
    if status == "images_unsupported":
        return "Images 接口不支持或返回 404"
    if status == "timeout":
        return "请求超时"
    if status == "network_error":
        return "网络或本地 relay 连接失败"
    if status and status != "unknown":
        return f"{status}" + (f"：{message}" if message else "")
    return "没有缓存记录"


def image_generation_capability_from_cache(entry: dict[str, Any]) -> str:
    status = str(entry.get("status") or "")
    if status == "verified":
        age = seconds_since_iso(entry.get("last_success_at"))
        if age is None or age <= IMAGE_PROVIDER_SUCCESS_TTL_SECONDS:
            return "verified"
    if image_provider_cache_unusable(entry):
        if status in {"image_generation_disabled", "responses_unsupported", "images_unsupported"}:
            return "unsupported"
        return "unstable"
    return "unknown"


def image_provider_attempt_status(route: str, result: dict[str, Any]) -> str:
    if result.get("ok"):
        return "verified"
    if result.get("status") == "no_image_result":
        return "images_unsupported" if route == "images" else "responses_unsupported"
    error_data = result.get("error") or {}
    status = error_data.get("status")
    category = str(error_data.get("category") or classify_api_failure(error_data)).lower()
    message = str(error_data.get("message") or "").lower()
    if "image generation is not enabled" in message:
        return "image_generation_disabled"
    if category == "timeout":
        return "timeout"
    if category == "network_error":
        return "network_error"
    if category == "unsupported_router":
        return "images_unsupported" if route == "images" else "responses_unsupported"
    if route == "images" and status in {404, 405}:
        return "images_unsupported"
    if route == "responses" and status == 502:
        return "responses_upstream_502"
    if route == "responses" and isinstance(status, int) and status >= 500:
        return "responses_server_error"
    return category or "api_error"


def record_image_provider_attempt(base_url: str, base_url_source: str, route: str, result: dict[str, Any]) -> None:
    if result.get("status") == "dry_run":
        return
    provider_id = image_provider_id_from_source(base_url_source)
    if not provider_id:
        return
    status = image_provider_attempt_status(route, result)
    cache = image_provider_health_cache()
    providers = cache.setdefault("providers", {})
    if not isinstance(providers, dict):
        providers = {}
        cache["providers"] = providers
    now = now_iso()
    entry = providers.get(provider_id)
    if not isinstance(entry, dict):
        entry = {}
    entry.update({
        "provider_id": provider_id,
        "base_url": base_url,
        "base_url_source": base_url_source,
        "last_route": route,
        "last_seen_at": now,
        "status": status,
    })
    if result.get("ok"):
        entry["last_success_at"] = now
        entry["last_error"] = None
        entry["image_generation_capability"] = "verified"
    else:
        entry["last_error_at"] = now
        entry["last_error"] = result.get("error")
        entry["image_generation_capability"] = image_generation_capability_from_cache(entry)
    providers[provider_id] = entry
    try:
        write_image_provider_health_cache(cache)
    except Exception as exc:  # noqa: BLE001
        stderr_event("image_provider_health_cache_write_failed", provider_id=provider_id, error=str(exc))


def aimami_state_provider_records() -> list[dict[str, Any]]:
    data = aimami_state_data()
    providers = data.get("providers") if isinstance(data, dict) else None
    if not isinstance(providers, list):
        return []
    records: list[dict[str, Any]] = []
    for order, provider in enumerate(providers):
        if not isinstance(provider, dict):
            continue
        provider_id = provider.get("id")
        if not isinstance(provider_id, str) or not provider_id:
            continue
        base_url = aimami_state_provider_base_url(provider_id)
        if not base_url:
            continue
        records.append({"name": provider_id, "provider": provider, "base_url": base_url, "order": order})
    return records


def image_model_provider_entries(args: argparse.Namespace) -> list[dict[str, Any]]:
    if getattr(args, "base_url", None):
        return []
    if dedicated_base_url_candidate():
        return []
    if getattr(args, "route", "responses") not in {"responses", "auto"}:
        return []
    image_model = getattr(args, "image_model", DEFAULT_IMAGE_MODEL)
    if not isinstance(image_model, str) or not image_model:
        return []
    model = getattr(args, "model", DEFAULT_MODEL)
    model_source = getattr(args, "model_source", "cli" if model != DEFAULT_MODEL else "default")
    if model_source == "cli" and model not in {DEFAULT_MODEL, image_model}:
        return []

    entries: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    seen_provider_ids: set[str] = set()

    def add_entry(*, base_url: str, source: str, provider_id: str, provider: dict[str, Any], order: int, source_kind: str) -> None:
        if base_url in seen_urls:
            return
        cache_entry = image_provider_cache_entry(provider_id)
        entries.append({
            "base_url": base_url,
            "base_url_source": source,
            "provider_id": provider_id,
            "source_kind": source_kind,
            "model": image_model,
            "healthScore": provider.get("healthScore"),
            "latencyMs": provider.get("latencyMs"),
            "lastError": provider.get("lastError"),
            "order": order,
            "capability_cache": cache_entry,
            "image_generation_capability": image_generation_capability_from_cache(cache_entry),
            "temporarily_unusable": image_provider_cache_unusable(cache_entry),
        })
        seen_urls.add(base_url)
        seen_provider_ids.add(provider_id)

    for order, record in enumerate(codex_provider_records()):
        provider = record["provider"]
        base_url = record["base_url"]
        provider_name = record["name"]
        provider_id = provider_identity_from_base_url(base_url)
        if not provider_id or provider_id != provider_name:
            continue
        model = codex_provider_display_model(provider, provider_name)
        if model != image_model:
            continue
        state_provider = aimami_state_provider_by_id(provider_id)
        provider_for_sort = state_provider if isinstance(state_provider, dict) else provider
        add_entry(
            base_url=base_url,
            source=f"codex_config:{provider_name}",
            provider_id=provider_id,
            provider=provider_for_sort,
            order=order,
            source_kind="codex_config",
        )

    state_offset = 10_000
    for record in aimami_state_provider_records():
        provider = record["provider"]
        provider_id = record["name"]
        if provider_id in seen_provider_ids:
            continue
        model = provider.get("model")
        if model != image_model:
            continue
        add_entry(
            base_url=record["base_url"],
            source=f"aimami_state:{provider_id}",
            provider_id=provider_id,
            provider=provider,
            order=state_offset + int(record.get("order") or 0),
            source_kind="aimami_state",
        )

    def sort_key(item: dict[str, Any]) -> tuple[int, int, int, int, int]:
        cache = item.get("capability_cache") if isinstance(item.get("capability_cache"), dict) else {}
        capability = image_generation_capability_from_cache(cache)
        health = item.get("healthScore")
        latency = item.get("latencyMs")
        last_error = item.get("lastError")
        if capability == "verified":
            capability_rank = 0
        elif item.get("temporarily_unusable"):
            capability_rank = 3
        else:
            capability_rank = 1 if not last_error else 2
        return (
            capability_rank,
            0 if not last_error else 1,
            -int(health) if isinstance(health, int) else 0,
            int(latency) if isinstance(latency, int) else 10**9,
            int(item.get("order") or 0),
        )

    return sorted(entries, key=sort_key)


def image_provider_candidate_notes(candidates: list[tuple[str, str]]) -> dict[str, Any]:
    dedicated = dedicated_base_url_candidate()
    if dedicated and not candidates:
        return {
            "primary_image_provider": dedicated[1],
            "backup_image_providers": [],
            "skipped_image_provider_candidates": [],
            "image_provider_health_notes": [],
            "image_provider_candidates_discovered": [],
            "image_provider_candidates_skipped": [],
            "image_provider_capability_cache": {"version": 1, "providers": {}},
            "image_generation_capability": "dedicated_provider_unverified",
            "image_provider_selection_reason": "dedicated Henry Image provider",
        }
    primary = candidates[0] if candidates else None
    backups = candidates[1:] if len(candidates) > 1 else []
    skipped: list[dict[str, Any]] = []
    notes: list[dict[str, Any]] = []
    for base_url, source in candidates:
        provider_id = image_provider_id_from_source(source)
        cache_entry = image_provider_cache_entry(provider_id)
        temporarily_unusable = image_provider_cache_unusable(cache_entry)
        note = {
            "base_url": base_url,
            "base_url_source": source,
            "provider_id": provider_id,
            "role": "primary" if primary and source == primary[1] else "backup",
            "model_visible": True,
            "image_generation_capability": image_generation_capability_from_cache(cache_entry),
            "capability_cache": cache_entry,
            "recommended_for_auto": not temporarily_unusable,
        }
        if temporarily_unusable:
            note["status"] = "temporarily_unusable_image_provider"
            note["reason"] = image_provider_cache_reason(cache_entry)
            skipped.append(dict(note))
        else:
            note["status"] = "candidate"
        notes.append(note)
    return {
        "primary_image_provider": primary[1] if primary else None,
        "backup_image_providers": [source for _, source in backups],
        "skipped_image_provider_candidates": skipped,
        "image_provider_health_notes": notes,
        "image_provider_candidates_discovered": notes,
        "image_provider_candidates_skipped": skipped,
        "image_provider_capability_cache": image_provider_health_cache(),
        "image_generation_capability": notes[0].get("image_generation_capability") if notes else "unknown",
        "image_provider_selection_reason": (
            "dynamic AiMaMi/Codex image provider discovery"
            if notes
            else "no matching image provider discovered"
        ),
    }


def active_image_model_base_url_candidates(args: argparse.Namespace) -> list[tuple[str, str]]:
    candidates = image_model_base_url_candidates(args)
    if not candidates:
        return []
    if getattr(args, "candidate_policy", "auto") != "auto":
        return candidates
    route = getattr(args, "route", "responses")
    if route not in {"responses", "auto"}:
        return candidates
    active: list[tuple[str, str]] = []
    for base_url, source in candidates:
        provider_id = image_provider_id_from_source(source)
        if image_provider_cache_unusable(image_provider_cache_entry(provider_id)):
            continue
        active.append((base_url, source))
    return active


def image_model_base_url_candidates(args: argparse.Namespace) -> list[tuple[str, str]]:
    return [(item["base_url"], item["base_url_source"]) for item in image_model_provider_entries(args)]


def effective_responses_model(args: argparse.Namespace, base_url_source: str | None) -> tuple[str, str]:
    codex_model, codex_model_source = codex_responses_model(base_url_source)
    model_source = getattr(args, "model_source", "cli_or_default")
    if codex_model and codex_model_source and (args.model == DEFAULT_MODEL or model_source != "cli"):
        return codex_model, codex_model_source
    return args.model, getattr(args, "model_source", "cli_or_default")


def codex_provider_auth_candidates(base_url_source: str | None) -> list[tuple[str, str]]:
    provider = codex_provider_from_source(base_url_source)
    if not isinstance(provider, dict):
        return []
    candidates: list[tuple[str, str]] = []
    env_key = provider.get("env_key") or provider.get("api_key_env")
    if isinstance(env_key, str) and env_key:
        env_value = env_get(env_key)
        if env_value:
            candidates.append((env_value, f"codex_config:env_key:{env_key}"))
    api_key = provider.get("api_key")
    if isinstance(api_key, str) and api_key:
        candidates.append((api_key, "codex_config:api_key"))
    return candidates


def auth_candidates(preferred_env: str | None = None, base_url_source: str | None = None) -> list[tuple[str | None, str]]:
    candidates: list[tuple[str | None, str]] = []
    requires_codex_auth = codex_provider_requires_auth(base_url_source)
    if requires_codex_auth is True:
        token, _ = codex_access_token()
        if token:
            candidates.append((token, "codex_auth:access_token"))
        candidates.extend(codex_provider_auth_candidates(base_url_source))
    elif requires_codex_auth is False:
        candidates.extend(codex_provider_auth_candidates(base_url_source))
        candidates.append((None, "codex_config:no_auth"))
    else:
        candidates.extend(codex_provider_auth_candidates(base_url_source))

    seen_values: set[str] = {value for value, _ in candidates if value is not None}
    for value, source in api_key_candidates(preferred_env):
        if value in seen_values:
            continue
        candidates.append((value, source))
        seen_values.add(value)
    return candidates


def is_local_base_url(base_url: str) -> bool:
    return core_providers.is_local_base_url(base_url)


def is_azure_like(base_url: str, base_url_source: str | None = None) -> bool:
    return core_providers.is_azure_like(base_url, base_url_source)


def azure_openai_v1_like(base_url: str) -> bool:
    return core_providers.azure_openai_v1_like(base_url)


def provider_family(base_url: str, base_url_source: str | None = None) -> str:
    return core_providers.provider_family(base_url, base_url_source)


def openai_org_project_headers() -> tuple[dict[str, str], dict[str, str]]:
    headers: dict[str, str] = {}
    sources: dict[str, str] = {}
    org, org_source = env_value(OPENAI_ORG_ENV_NAMES)
    project, project_source = env_value(OPENAI_PROJECT_ENV_NAMES)
    if org:
        headers["OpenAI-Organization"] = org
        sources["OpenAI-Organization"] = org_source or "env"
    if project:
        headers["OpenAI-Project"] = project
        sources["OpenAI-Project"] = project_source or "env"
    return headers, sources


def resolve_config_secret(value: Any) -> tuple[str | None, str | None]:
    if isinstance(value, dict):
        for key in ("env", "env_key", "environment", "from_env"):
            env_name = value.get(key)
            if isinstance(env_name, str) and env_name and env_get(env_name):
                return env_get(env_name), f"env:{env_name}"
        raw = value.get("value")
        if isinstance(raw, str):
            return raw, "codex_config"
        return None, None
    if not isinstance(value, str) or not value:
        return None, None
    text = value.strip()
    if text.lower().startswith("env:"):
        env_name = text.split(":", 1)[1].strip()
        return (env_get(env_name), f"env:{env_name}") if env_name and env_get(env_name) else (None, None)
    match = re.fullmatch(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?", text)
    if match:
        env_name = match.group(1)
        return (env_get(env_name), f"env:{env_name}") if env_get(env_name) else (None, None)
    return text, "codex_config"


def provider_config_headers(base_url_source: str | None) -> tuple[dict[str, str], dict[str, str]]:
    provider = codex_provider_from_source(base_url_source)
    headers: dict[str, str] = {}
    sources: dict[str, str] = {}
    if not isinstance(provider, dict):
        return headers, sources
    for field in ("headers", "http_headers", "extra_headers"):
        raw = provider.get(field)
        if not isinstance(raw, dict):
            continue
        for name, value in raw.items():
            if not isinstance(name, str) or not name:
                continue
            resolved, source = resolve_config_secret(value)
            if resolved is None:
                continue
            headers[name] = resolved
            sources[name] = f"codex_config:{field}" if source == "codex_config" else source or f"codex_config:{field}"
    return headers, sources


def provider_config_query(base_url_source: str | None) -> tuple[dict[str, str], dict[str, str]]:
    provider = codex_provider_from_source(base_url_source)
    query: dict[str, str] = {}
    sources: dict[str, str] = {}
    if not isinstance(provider, dict):
        return query, sources
    for field in ("query", "query_params", "extra_query"):
        raw = provider.get(field)
        if not isinstance(raw, dict):
            continue
        for name, value in raw.items():
            if not isinstance(name, str) or not name:
                continue
            resolved, source = resolve_config_secret(value)
            if resolved is None:
                continue
            query[name] = resolved
            sources[name] = f"codex_config:{field}" if source == "codex_config" else source or f"codex_config:{field}"
    api_version = provider.get("api_version") or provider.get("api-version")
    resolved, source = resolve_config_secret(api_version)
    if resolved:
        query.setdefault("api-version", resolved)
        sources.setdefault("api-version", source or "codex_config:api_version")
    return query, sources


def azure_api_version(base_url_source: str | None = None) -> tuple[str, str]:
    query, sources = provider_config_query(base_url_source)
    if query.get("api-version"):
        return query["api-version"], sources.get("api-version") or "codex_config"
    value, source = env_value(AZURE_API_VERSION_ENV_NAMES)
    if value:
        return value, source or "env"
    return DEFAULT_AZURE_API_VERSION, "default"


def configured_api_key_header_name(base_url: str, base_url_source: str | None, auth_source: str | None = None) -> str:
    provider = codex_provider_from_source(base_url_source)
    if isinstance(provider, dict):
        for field in ("api_key_header", "api_key_header_name"):
            value = provider.get(field)
            if isinstance(value, str) and value:
                return value
    source = (auth_source or "").upper()
    if "X_API_KEY" in source or "X-API-KEY" in source:
        return "x-api-key"
    if is_azure_like(base_url, base_url_source) or "AZURE" in source or "AOAI" in source:
        return "api-key"
    return "api-key"


def provider_auth_type(base_url_source: str | None) -> str | None:
    provider = codex_provider_from_source(base_url_source)
    if not isinstance(provider, dict):
        return None
    for field in ("auth_type", "auth_mode", "auth_kind"):
        value = provider.get(field)
        if isinstance(value, str) and value:
            normalized = value.strip().lower().replace("_", "-")
            if normalized in {"api-key", "api-key-header", "header-api-key"}:
                return "api-key-header"
            if normalized in {"none", "no-auth", "noauth", "anonymous"}:
                return "no-auth"
            if normalized in {"bearer", "authorization-bearer"}:
                return "bearer"
    return None


def auth_profile_summary(profile: AuthProfile) -> dict[str, Any]:
    return core_auth.auth_profile_summary(profile)


def dedupe_auth_profiles(profiles: list[AuthProfile]) -> list[AuthProfile]:
    return core_auth.dedupe_auth_profiles(profiles)


def auth_profiles(
    base_url: str,
    base_url_source: str | None = None,
    preferred_env: str | None = None,
    route: str | None = None,
) -> list[AuthProfile]:
    family = provider_family(base_url, base_url_source)
    profiles: list[AuthProfile] = []
    config_headers, config_header_sources = provider_config_headers(base_url_source)
    config_query, config_query_sources = provider_config_query(base_url_source)
    org_headers, org_sources = openai_org_project_headers()
    auth_type = provider_auth_type(base_url_source)

    def merged(extra_headers: dict[str, str], extra_sources: dict[str, str], extra_query: dict[str, str], extra_query_sources: dict[str, str]) -> tuple[dict[str, str], dict[str, str], dict[str, str], dict[str, str]]:
        headers = dict(config_headers)
        header_sources = dict(config_header_sources)
        if family not in {"azure", "local_relay"}:
            headers.update(org_headers)
            header_sources.update(org_sources)
        headers.update(extra_headers)
        header_sources.update(extra_sources)
        query = dict(config_query)
        query_sources = dict(config_query_sources)
        query.update(extra_query)
        query_sources.update(extra_query_sources)
        return headers, header_sources, query, query_sources

    def add_no_auth(source: str, reason: str) -> None:
        headers, header_sources, query, query_sources = merged({}, {}, {}, {})
        profiles.append(AuthProfile(None, source, "no-auth", headers, query, header_sources, query_sources, family, reason))

    def add_bearer(value: str, source: str, reason: str) -> None:
        headers, header_sources, query, query_sources = merged(
            {"Authorization": f"Bearer {value}"},
            {"Authorization": source},
            {},
            {},
        )
        profiles.append(AuthProfile(value, source, "bearer", headers, query, header_sources, query_sources, family, reason))

    def add_api_key_header(value: str, source: str, reason: str) -> None:
        header_name = configured_api_key_header_name(base_url, base_url_source, source)
        extra_query: dict[str, str] = {}
        extra_query_sources: dict[str, str] = {}
        if family == "azure" and "api-version" not in config_query:
            version, version_source = azure_api_version(base_url_source)
            extra_query["api-version"] = version
            extra_query_sources["api-version"] = version_source
        headers, header_sources, query, query_sources = merged(
            {header_name: value},
            {header_name: source},
            extra_query,
            extra_query_sources,
        )
        profiles.append(AuthProfile(value, source, "api-key-header", headers, query, header_sources, query_sources, family, reason))

    def add_config_injected_profile() -> None:
        auth_header_name = next((name for name in config_headers if name.lower() == "authorization"), None)
        api_key_header_name = next(
            (
                name
                for name in config_headers
                if name.lower() in {"api-key", "x-api-key"} or "api_key" in name.lower().replace("-", "_")
            ),
            None,
        )
        auth_query_name = next((name for name in config_query if name.lower() != "api-version"), None)
        if not (auth_header_name or api_key_header_name or auth_query_name):
            return
        headers, header_sources, query, query_sources = merged({}, {}, {}, {})
        if auth_header_name:
            source = config_header_sources.get(auth_header_name) or "codex_config:headers"
            raw_value = config_headers.get(auth_header_name)
            value = raw_value.split(None, 1)[1] if isinstance(raw_value, str) and raw_value.lower().startswith("bearer ") and len(raw_value.split(None, 1)) == 2 else raw_value
            profiles.append(AuthProfile(value, source, "bearer", headers, query, header_sources, query_sources, family, "Codex provider injected Authorization header"))
        elif api_key_header_name:
            source = config_header_sources.get(api_key_header_name) or "codex_config:headers"
            profiles.append(AuthProfile(config_headers.get(api_key_header_name), source, "api-key-header", headers, query, header_sources, query_sources, family, "Codex provider injected API-key header"))
        elif auth_query_name:
            source = config_query_sources.get(auth_query_name) or "codex_config:query"
            profiles.append(AuthProfile(config_query.get(auth_query_name), source, "no-auth", headers, query, header_sources, query_sources, family, "Codex provider injected query parameters"))

    if family == "local_relay" and auth_type in {None, "no-auth"}:
        add_no_auth("local_relay:no_auth", "local relay base URL")

    add_config_injected_profile()

    auth_items = auth_candidates(preferred_env, base_url_source)
    if family == "local_relay" and codex_provider_requires_auth(base_url_source) is not True:
        explicit_env_names = {
            raw.strip()
            for raw in (preferred_env or "").split(",")
            if raw.strip()
        }
        auth_items = [
            (value, source)
            for value, source in auth_items
            if value is None or source.startswith("codex_config:") or source in explicit_env_names
        ]
    if family == "azure":
        auth_items = [
            item
            for _, item in sorted(
                enumerate(auth_items),
                key=lambda indexed: (
                    0
                    if str(indexed[1][1]).startswith("codex_config:")
                    else 1
                    if any(token in str(indexed[1][1]).upper() for token in ("AZURE", "AOAI"))
                    else 2,
                    indexed[0],
                ),
            )
        ]

    for value, source in auth_items:
        if value is None:
            add_no_auth(source, "Codex provider allows no-auth")
            continue
        if family == "azure":
            if auth_type == "bearer":
                add_bearer(value, source, "Codex provider auth_type=bearer")
            else:
                add_api_key_header(value, source, "Azure/AOAI-like base URL")
                if azure_openai_v1_like(base_url) or auth_type == "bearer":
                    add_bearer(value, source, "Azure OpenAI-compatible /openai/v1 fallback")
        elif auth_type == "api-key-header":
            add_api_key_header(value, source, "Codex provider auth_type=api-key-header")
        elif auth_type == "no-auth":
            add_no_auth(source, "Codex provider auth_type=no-auth")
        else:
            add_bearer(value, source, "OpenAI-compatible default")
            source_upper = source.upper()
            if "X_API_KEY" in source_upper or "HEADER_API_KEY" in source_upper:
                add_api_key_header(value, source, "API key env name suggests header auth")

    return dedupe_auth_profiles(profiles)


def base_url_env_candidates() -> list[str]:
    names = list(DEFAULT_BASE_URL_ENV_NAMES)
    for name in sorted(os.environ):
        if any(pattern.fullmatch(name) for pattern in BASE_URL_ENV_NAME_PATTERNS):
            names.append(name)
    deduped: list[str] = []
    for name in names:
        if name and name not in deduped:
            deduped.append(name)
    return deduped


def base_url_candidates(base_url: str | None = None) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    if base_url:
        entries.append((normalize_base_url(base_url), "cli"))
    else:
        dedicated_candidate = dedicated_base_url_candidate()
        if dedicated_candidate:
            entries.append(dedicated_candidate)
        else:
            codex_candidate = codex_base_url_candidate()
            if codex_candidate:
                entries.append(codex_candidate)
            access = codex_access_info()
            model = access.get("model")
            provider = codex_provider_by_name(model if isinstance(model, str) else None)
            provider_base_url = provider.get("base_url") if isinstance(provider, dict) else None
            if isinstance(model, str) and isinstance(provider_base_url, str) and provider_base_url:
                entries.append((normalize_base_url(provider_base_url), f"codex_config:{model}"))
    for name in base_url_env_candidates():
        value = env_get(name)
        if value:
            entries.append((normalize_base_url(value), name))
    if not base_url:
        entries.append((DEFAULT_BASE_URL, "default"))

    deduped: list[tuple[str, str]] = []
    seen_urls: set[str] = set()
    for normalized, source in entries:
        if normalized in seen_urls:
            continue
        deduped.append((normalized, source))
        seen_urls.add(normalized)
    return deduped


def policy_base_url_candidates(args: argparse.Namespace) -> list[tuple[str, str]]:
    explicit_base_url = getattr(args, "base_url", None)
    candidates = base_url_candidates(explicit_base_url)
    policy = getattr(args, "candidate_policy", "auto")
    route = getattr(args, "route", "responses")
    if not explicit_base_url and dedicated_base_url_candidate():
        return candidates[:1]
    image_candidates = image_model_base_url_candidates(args)
    active_image_candidates = active_image_model_base_url_candidates(args)
    if explicit_base_url:
        return candidates[:1]
    if image_candidates and route in {"responses", "auto"}:
        if policy == "strict":
            return image_candidates[:1]
        if policy == "all":
            merged: list[tuple[str, str]] = []
            seen: set[str] = set()
            for entry in image_candidates + candidates:
                if entry[0] in seen:
                    continue
                merged.append(entry)
                seen.add(entry[0])
            return merged
        if policy == "auto":
            return active_image_candidates
    if policy == "all":
        return candidates
    if policy == "strict":
        return candidates[:1]
    if route == "auto":
        return candidates
    return candidates[:1]


def known_secret_values() -> list[str]:
    values: list[str] = []
    try:
        values.extend(value for value, _ in api_key_candidates(None))
    except Exception:  # noqa: BLE001
        pass
    try:
        token, _ = codex_access_token()
        if token:
            values.append(token)
    except Exception:  # noqa: BLE001
        pass
    try:
        for names in (OPENAI_ORG_ENV_NAMES, OPENAI_PROJECT_ENV_NAMES):
            for name in names:
                value = env_get(name)
                if value:
                    values.append(value)
    except Exception:  # noqa: BLE001
        pass
    try:
        data = codex_config_data()
        providers = data.get("model_providers") if isinstance(data, dict) and isinstance(data.get("model_providers"), dict) else {}
        for provider in providers.values():
            if not isinstance(provider, dict):
                continue
            api_key = provider.get("api_key")
            if isinstance(api_key, str) and api_key:
                values.append(api_key)
            env_key = provider.get("env_key") or provider.get("api_key_env")
            if isinstance(env_key, str) and env_key and env_get(env_key):
                values.append(env_get(env_key) or "")
            for field in ("headers", "http_headers", "extra_headers"):
                raw = provider.get(field)
                if not isinstance(raw, dict):
                    continue
                for header_value in raw.values():
                    resolved, _ = resolve_config_secret(header_value)
                    if resolved:
                        values.append(resolved)
            for field in ("query", "query_params", "extra_query"):
                raw = provider.get(field)
                if not isinstance(raw, dict):
                    continue
                for name, query_value in raw.items():
                    if str(name).lower() == "api-version":
                        continue
                    resolved, _ = resolve_config_secret(query_value)
                    if resolved:
                        values.append(resolved)
    except Exception:  # noqa: BLE001
        pass
    deduped: list[str] = []
    for value in values:
        if len(value) < 6 or value in deduped:
            continue
        deduped.append(value)
    return deduped


def env_candidates(args: argparse.Namespace) -> list[dict[str, Any]]:
    key_names = api_key_env_candidates(args.api_key_env)
    base_entries = base_url_candidates(args.base_url)

    model, model_source = configured_model(args.model, DEFAULT_MODEL, DEFAULT_MODEL_ENV_NAMES)
    image_model, image_model_source = configured_model(args.image_model, DEFAULT_IMAGE_MODEL, DEFAULT_IMAGE_MODEL_ENV_NAMES)
    candidates: list[dict[str, Any]] = []
    for base_url, base_url_source in base_entries:
        for key_name in key_names:
            candidates.append({
                "base_url": base_url,
                "base_url_source": base_url_source,
                "base_url_host": parse.urlparse(base_url).netloc or base_url,
                "api_key_env": key_name,
                "api_key": "set" if env_get(key_name) else "missing",
                "model": model,
                "model_source": model_source,
                "image_model": image_model,
                "image_model_source": image_model_source,
                "routes": ["responses", "images"],
            })
    return candidates


def choose_env_candidate(args: argparse.Namespace) -> dict[str, Any]:
    candidates = env_candidates(args)
    selected = next((item for item in candidates if item["api_key"] == "set"), candidates[0])
    args.base_url = selected["base_url"]
    args.api_key_env = selected["api_key_env"]
    args.model = selected["model"]
    args.image_model = selected["image_model"]
    return selected


def parse_size(size: str) -> tuple[int, int] | None:
    return core_validate.parse_size(size)


def validate_common(args: argparse.Namespace) -> None:
    return core_validate.validate_common(
        args,
        qualities=QUALITIES,
        output_formats=OUTPUT_FORMATS,
        image_response_formats=IMAGES_RESPONSE_FORMATS,
        image_compat_modes=IMAGES_COMPAT_MODES,
        input_fidelities=INPUT_FIDELITIES,
        backgrounds=BACKGROUNDS,
        moderations=MODERATIONS,
        routes=ROUTES,
    )


def is_http_url(value: str) -> bool:
    parsed = parse.urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def is_data_image_url(value: str) -> bool:
    return value.startswith("data:image/") and ";base64," in value


def encode_image(path_raw: str) -> dict[str, str]:
    if is_http_url(path_raw) or is_data_image_url(path_raw):
        return {"type": "input_image", "image_url": path_raw}
    path = Path(path_raw)
    if not path.exists():
        raise ValueError(f"Image file not found: {path}")
    if path.stat().st_size > MAX_IMAGE_BYTES:
        raise ValueError(f"Image exceeds 50MB limit: {path}")
    mime, _ = mimetypes.guess_type(path.name)
    mime = mime or "image/png"
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return {"type": "input_image", "image_url": f"data:{mime};base64,{b64}"}


def build_input(prompt: str, images: list[str], image_file_ids: list[str]) -> str | list[dict[str, Any]]:
    if not images and not image_file_ids:
        return prompt
    content: list[dict[str, Any]] = [{"type": "input_text", "text": prompt}]
    content.extend(encode_image(path) for path in images)
    content.extend({"type": "input_image", "file_id": file_id} for file_id in image_file_ids)
    return [{"role": "user", "content": content}]


def build_tool(args: argparse.Namespace, mask: str | None = None, mask_file_id: str | None = None) -> dict[str, Any]:
    tool: dict[str, Any] = {
        "type": "image_generation",
        "size": args.size,
        "quality": args.quality,
        "output_format": args.output_format,
        "background": args.background,
        "moderation": args.moderation,
    }
    if args.output_compression is not None:
        tool["output_compression"] = args.output_compression
    if args.partial_images:
        tool["partial_images"] = args.partial_images
    if mask:
        tool["input_image_mask"] = encode_image(mask)
    if mask_file_id:
        tool["input_image_mask"] = {"file_id": mask_file_id}
    return tool


def build_payload(
    *,
    prompt: str,
    args: argparse.Namespace,
    images: list[str] | None = None,
    image_file_ids: list[str] | None = None,
    mask: str | None = None,
    mask_file_id: str | None = None,
) -> dict[str, Any]:
    images = images or []
    image_file_ids = image_file_ids or []
    return {
        "model": args.model,
        "input": build_input(prompt, images, image_file_ids),
        "tools": [build_tool(args, mask, mask_file_id)],
        "tool_choice": {"type": "image_generation"},
    }


def build_images_payload(prompt: str, args: argparse.Namespace, compat_mode: str | None = None) -> dict[str, Any]:
    image_model = args.image_model or args.model
    mode = compat_mode or args.images_compat
    if mode == "auto":
        mode = "openai"
    payload: dict[str, Any] = {
        "model": image_model,
        "prompt": prompt,
        "n": args.n,
        "size": args.size,
    }
    if args.images_response_format != "auto":
        payload["response_format"] = args.images_response_format
    if mode == "minimal":
        return payload
    if args.quality != "auto":
        payload["quality"] = args.quality
    if args.background != "auto":
        payload["background"] = args.background
    if args.output_format != DEFAULT_OUTPUT_FORMAT:
        payload["output_format"] = args.output_format
    if args.output_compression is not None:
        payload["output_compression"] = args.output_compression
    if args.moderation != "auto":
        payload["moderation"] = args.moderation
    return payload


def multipart_quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def read_image_part(path_raw: str, timeout: int) -> tuple[str, str, bytes]:
    if is_data_image_url(path_raw):
        header, encoded = path_raw.split(",", 1)
        mime = header[5:].split(";", 1)[0] or "image/png"
        data = base64.b64decode(encoded)
        if len(data) > MAX_IMAGE_BYTES:
            raise ValueError("Image exceeds 50MB limit.")
        extension = mimetypes.guess_extension(mime) or ".png"
        return f"image{extension}", mime, data
    if is_http_url(path_raw):
        with request.urlopen(path_raw, timeout=timeout) as response:
            data = response.read(MAX_IMAGE_BYTES + 1)
            if len(data) > MAX_IMAGE_BYTES:
                raise ValueError(f"Image exceeds 50MB limit: {path_raw}")
            content_type = response.headers.get("content-type", "image/png").split(";", 1)[0]
        parsed = parse.urlparse(path_raw)
        filename = Path(parsed.path).name or "image"
        if "." not in filename:
            filename += mimetypes.guess_extension(content_type) or ".png"
        return filename, content_type or "image/png", data
    path = Path(path_raw)
    if not path.exists():
        raise ValueError(f"Image file not found: {path}")
    if path.stat().st_size > MAX_IMAGE_BYTES:
        raise ValueError(f"Image exceeds 50MB limit: {path}")
    mime, _ = mimetypes.guess_type(path.name)
    return path.name, mime or "image/png", path.read_bytes()


def build_images_edit_request(
    prompt: str,
    args: argparse.Namespace,
    compat_mode: str | None = None,
) -> tuple[list[tuple[str, str]], list[tuple[str, str, str, bytes]], dict[str, Any]]:
    images = list(getattr(args, "image", []) or [])
    image_file_ids = list(getattr(args, "image_file_id", []) or [])
    if image_file_ids:
        raise ValueError("images edit route requires --image files/URLs/data URLs; --image-file-id is Responses-only.")
    if not images:
        raise ValueError("images edit route requires at least one --image.")
    if getattr(args, "mask_file_id", None):
        raise ValueError("images edit route requires --mask files/URLs/data URLs; --mask-file-id is Responses-only.")

    image_model = args.image_model or args.model
    mode = compat_mode or args.images_compat
    if mode == "auto":
        mode = "openai"
    fields: list[tuple[str, str]] = [
        ("model", image_model),
        ("prompt", prompt),
        ("n", str(args.n)),
    ]
    if args.size != "auto":
        fields.append(("size", args.size))
    if args.images_response_format != "auto":
        fields.append(("response_format", args.images_response_format))
    if args.input_fidelity != "auto":
        fields.append(("input_fidelity", args.input_fidelity))
    if mode != "minimal":
        if args.quality != "auto":
            fields.append(("quality", args.quality))
        if args.background != "auto":
            fields.append(("background", args.background))
        if args.output_format != DEFAULT_OUTPUT_FORMAT:
            fields.append(("output_format", args.output_format))
        if args.output_compression is not None:
            fields.append(("output_compression", str(args.output_compression)))
        if args.moderation != "auto":
            fields.append(("moderation", args.moderation))

    files: list[tuple[str, str, str, bytes]] = []
    file_summaries: list[dict[str, Any]] = []
    for image in images:
        filename, mime, data = read_image_part(image, args.timeout)
        files.append(("image", filename, mime, data))
        file_summaries.append({"field": "image", "filename": filename, "content_type": mime, "bytes": len(data)})
    if getattr(args, "mask", None):
        filename, mime, data = read_image_part(args.mask, args.timeout)
        files.append(("mask", filename, mime, data))
        file_summaries.append({"field": "mask", "filename": filename, "content_type": mime, "bytes": len(data)})

    summary: dict[str, Any] = {
        "payload_kind": "multipart",
        "model": image_model,
        "prompt": prompt,
        "n": args.n,
        "size": args.size,
        "input_fidelity": args.input_fidelity,
        "image_count": len(images),
        "has_mask": bool(getattr(args, "mask", None)),
        "fields": {name: value for name, value in fields},
        "files": file_summaries,
    }
    return fields, files, summary


def encode_multipart(
    fields: list[tuple[str, str]],
    files: list[tuple[str, str, str, bytes]],
) -> tuple[bytes, str]:
    boundary = f"henry-image-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields:
        chunks.extend([
            f"--{boundary}\r\n".encode("ascii"),
            f'Content-Disposition: form-data; name="{multipart_quote(name)}"\r\n\r\n'.encode("utf-8"),
            str(value).encode("utf-8"),
            b"\r\n",
        ])
    for name, filename, content_type, data in files:
        chunks.extend([
            f"--{boundary}\r\n".encode("ascii"),
            (
                f'Content-Disposition: form-data; name="{multipart_quote(name)}"; '
                f'filename="{multipart_quote(filename)}"\r\n'
            ).encode("utf-8"),
            f"Content-Type: {content_type}\r\n\r\n".encode("ascii"),
            data,
            b"\r\n",
        ])
    chunks.append(f"--{boundary}--\r\n".encode("ascii"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def parse_error_body(status: int, detail: str) -> dict[str, Any]:
    return core_request.parse_error_body(status, detail)


def classify_api_failure(error_data: dict[str, Any] | None) -> str:
    return core_request.classify_api_failure(error_data)


def failure_error_obj(error_data: dict[str, Any] | None) -> dict[str, Any]:
    return core_request.failure_error_obj(error_data)


def url_with_query(url: str, query_values: dict[str, str] | None) -> str:
    if not query_values:
        return url
    parsed = parse.urlparse(url)
    query = dict(parse.parse_qsl(parsed.query, keep_blank_values=True))
    query.update({key: str(value) for key, value in query_values.items() if value is not None})
    return parse.urlunparse(parsed._replace(query=parse.urlencode(query)))


def request_json(
    url: str,
    api_key: str | None,
    payload: dict[str, Any],
    retries: int,
    timeout: int,
    auth_profile: AuthProfile | None = None,
) -> ApiResult:
    body = json.dumps(payload).encode("utf-8")
    last_error: dict[str, Any] | None = None
    request_id: str | None = None
    started = time.monotonic()
    for attempt in range(retries + 1):
        headers = dict(auth_profile.headers) if auth_profile is not None else {}
        headers["Content-Type"] = "application/json"
        if auth_profile is None and api_key is not None:
            headers["Authorization"] = f"Bearer {api_key}"
        req = request.Request(
            url_with_query(url, auth_profile.query if auth_profile is not None else None),
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=timeout) as response:
                request_id = response.headers.get("x-request-id")
                data = json.loads(response.read().decode("utf-8"))
                latency = int((time.monotonic() - started) * 1000)
                return ApiResult(True, response.status, data, None, request_id, latency)
        except error.HTTPError as exc:
            request_id = exc.headers.get("x-request-id")
            detail = exc.read().decode("utf-8", errors="replace")
            last_error = parse_error_body(exc.code, detail)
            if exc.code not in RETRYABLE_STATUS or attempt >= retries:
                break
            retry_after = exc.headers.get("retry-after")
            sleep_for = int(retry_after) if retry_after and retry_after.isdigit() else min(2**attempt, 8)
            stderr_event("retry", attempt=attempt + 1, status=exc.code, sleep_seconds=sleep_for)
            time.sleep(sleep_for)
        except error.URLError as exc:
            last_error = {"status": None, "code": "url_error", "type": "network_error", "message": str(exc.reason)}
            if attempt >= retries:
                break
            sleep_for = min(2**attempt, 8)
            stderr_event("retry", attempt=attempt + 1, status=None, sleep_seconds=sleep_for)
            time.sleep(sleep_for)
        except TimeoutError as exc:
            last_error = {"status": None, "code": "timeout", "type": "network_error", "message": str(exc)}
            if attempt >= retries:
                break
            sleep_for = min(2**attempt, 8)
            stderr_event("retry", attempt=attempt + 1, status=None, sleep_seconds=sleep_for)
            time.sleep(sleep_for)
        except socket.timeout as exc:
            last_error = {"status": None, "code": "timeout", "type": "network_error", "message": str(exc)}
            if attempt >= retries:
                break
            sleep_for = min(2**attempt, 8)
            stderr_event("retry", attempt=attempt + 1, status=None, sleep_seconds=sleep_for)
            time.sleep(sleep_for)
    latency = int((time.monotonic() - started) * 1000)
    return ApiResult(False, last_error.get("status") if last_error else None, None, last_error, request_id, latency)


def request_multipart(
    url: str,
    api_key: str | None,
    fields: list[tuple[str, str]],
    files: list[tuple[str, str, str, bytes]],
    retries: int,
    timeout: int,
    auth_profile: AuthProfile | None = None,
) -> ApiResult:
    body, content_type = encode_multipart(fields, files)
    last_error: dict[str, Any] | None = None
    request_id: str | None = None
    started = time.monotonic()
    for attempt in range(retries + 1):
        headers = dict(auth_profile.headers) if auth_profile is not None else {}
        headers["Content-Type"] = content_type
        if auth_profile is None and api_key is not None:
            headers["Authorization"] = f"Bearer {api_key}"
        req = request.Request(
            url_with_query(url, auth_profile.query if auth_profile is not None else None),
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=timeout) as response:
                request_id = response.headers.get("x-request-id")
                data = json.loads(response.read().decode("utf-8"))
                latency = int((time.monotonic() - started) * 1000)
                return ApiResult(True, response.status, data, None, request_id, latency)
        except error.HTTPError as exc:
            request_id = exc.headers.get("x-request-id")
            detail = exc.read().decode("utf-8", errors="replace")
            last_error = parse_error_body(exc.code, detail)
            if exc.code not in RETRYABLE_STATUS or attempt >= retries:
                break
            retry_after = exc.headers.get("retry-after")
            sleep_for = int(retry_after) if retry_after and retry_after.isdigit() else min(2**attempt, 8)
            stderr_event("retry", attempt=attempt + 1, status=exc.code, sleep_seconds=sleep_for)
            time.sleep(sleep_for)
        except error.URLError as exc:
            last_error = {"status": None, "code": "url_error", "type": "network_error", "message": str(exc.reason)}
            if attempt >= retries:
                break
            sleep_for = min(2**attempt, 8)
            stderr_event("retry", attempt=attempt + 1, status=None, sleep_seconds=sleep_for)
            time.sleep(sleep_for)
        except TimeoutError as exc:
            last_error = {"status": None, "code": "timeout", "type": "network_error", "message": str(exc)}
            if attempt >= retries:
                break
            sleep_for = min(2**attempt, 8)
            stderr_event("retry", attempt=attempt + 1, status=None, sleep_seconds=sleep_for)
            time.sleep(sleep_for)
        except socket.timeout as exc:
            last_error = {"status": None, "code": "timeout", "type": "network_error", "message": str(exc)}
            if attempt >= retries:
                break
            sleep_for = min(2**attempt, 8)
            stderr_event("retry", attempt=attempt + 1, status=None, sleep_seconds=sleep_for)
            time.sleep(sleep_for)
    latency = int((time.monotonic() - started) * 1000)
    return ApiResult(False, last_error.get("status") if last_error else None, None, last_error, request_id, latency)


def collect_response_images(response: dict[str, Any]) -> list[str]:
    images: list[str] = []
    for item in response.get("output", []):
        if item.get("type") != "image_generation_call":
            continue
        for key in ("result", "image", "b64_json"):
            value = item.get(key)
            if isinstance(value, str) and value:
                images.append(value)
        for candidate in item.get("images", []) if isinstance(item.get("images"), list) else []:
            if isinstance(candidate, dict):
                for key in ("b64_json", "image", "result"):
                    value = candidate.get(key)
                    if isinstance(value, str) and value:
                        images.append(value)
    return images


def collect_images_api_images(response: dict[str, Any]) -> tuple[list[str], list[str]]:
    images: list[str] = []
    urls: list[str] = []
    for item in response.get("data", []) if isinstance(response.get("data"), list) else []:
        if not isinstance(item, dict):
            continue
        b64_value = item.get("b64_json") or item.get("image") or item.get("result")
        if isinstance(b64_value, str) and b64_value:
            images.append(b64_value)
        url_value = item.get("url")
        if isinstance(url_value, str) and url_value:
            urls.append(url_value)
    return images, urls


def request_id_from_response(response: dict[str, Any]) -> str | None:
    if isinstance(response.get("id"), str):
        return response["id"]
    return None


def output_paths(out: str, count: int, ext: str, force: bool) -> list[Path]:
    return core_request.output_paths(out, count, ext, force)


def write_image_bytes(images_raw: list[bytes], out: str, output_format: str, force: bool) -> list[dict[str, Any]]:
    return core_request.write_image_bytes(images_raw, out, output_format, force)


def decode_image_b64(value: str) -> bytes:
    return core_request.decode_image_b64(value)


def download_image(url: str, timeout: int) -> bytes:
    return core_request.download_image(url, timeout, is_data_image_url=is_data_image_url)


def write_images(images_b64: list[str], out: str, output_format: str, force: bool) -> list[dict[str, Any]]:
    return core_request.write_images(images_b64, out, output_format, force)


def write_manifest(out_path: str, manifest: dict[str, Any], force: bool) -> str:
    return core_request.write_manifest(out_path, manifest, force, redact=redact)


def job_id() -> str:
    return core_jobs.job_id()


def job_root(jobs_dir: str | None) -> Path:
    return core_jobs.job_root(jobs_dir or DEFAULT_JOBS_DIR, DEFAULT_JOBS_DIR)


def resolve_job_path(job: str, jobs_dir: str | None = None) -> Path:
    return core_jobs.resolve_job_path(job, jobs_dir, DEFAULT_JOBS_DIR)


def parse_duration_seconds(value: str) -> int:
    return core_jobs.parse_duration_seconds(value)


def read_json_file(path: Path) -> dict[str, Any] | None:
    if not path.exists() or path.stat().st_size == 0:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:  # noqa: BLE001
        return None


def tail_text(path: Path, line_count: int = 20) -> list[str]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()[-line_count:]
    except Exception:  # noqa: BLE001
        return []


def write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(redact(payload), ensure_ascii=False, indent=2)
    tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def update_job_json(job_file: Path, updates: dict[str, Any]) -> dict[str, Any]:
    metadata = read_json_file(job_file) or {}
    metadata.update(updates)
    write_json_file(job_file, metadata)
    return metadata


def append_job_event(stderr_path: Path, event: str, **data: Any) -> None:
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"event": event, **data}
    with stderr_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(redact(payload), ensure_ascii=False) + "\n")


def job_child_command(metadata: dict[str, Any]) -> str:
    command = str(metadata.get("command") or "henry.job")
    if command.startswith("henry.job."):
        return "henry." + command.removeprefix("henry.job.")
    return "henry.job.child"


def candidate_attempts_from_stderr(stderr_path: Path) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    for line in tail_text(stderr_path, 200):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        name = event.get("event")
        if name == "request_start":
            attempts.append({
                "route": event.get("route"),
                "endpoint": event.get("endpoint"),
                "auth_source": event.get("auth_source"),
                "auth_shape": event.get("auth_shape"),
                "header_names": event.get("header_names"),
                "query_names": event.get("query_names"),
                "provider_family": event.get("provider_family"),
                "adaptive_reason": event.get("adaptive_reason"),
                "base_url_source": event.get("base_url_source"),
            })
        elif name == "request_finish":
            if not attempts:
                attempts.append({})
            attempts[-1].update({
                "route": event.get("route", attempts[-1].get("route")),
                "endpoint": event.get("endpoint", attempts[-1].get("endpoint")),
                "auth_source": event.get("auth_source", attempts[-1].get("auth_source")),
                "auth_shape": event.get("auth_shape", attempts[-1].get("auth_shape")),
                "header_names": event.get("header_names", attempts[-1].get("header_names")),
                "query_names": event.get("query_names", attempts[-1].get("query_names")),
                "provider_family": event.get("provider_family", attempts[-1].get("provider_family")),
                "adaptive_reason": event.get("adaptive_reason", attempts[-1].get("adaptive_reason")),
                "base_url_source": event.get("base_url_source", attempts[-1].get("base_url_source")),
                "ok": event.get("ok"),
                "status": event.get("status"),
                "error_code": event.get("error_code"),
                "request_id": event.get("request_id"),
                "latency_ms": event.get("latency_ms"),
            })
        elif name in {"retry", "route_fallback", "base_url_fallback", "payload_fallback", "api_key_fallback"} and attempts:
            attempts[-1].setdefault("events", []).append(redact(event))
    return attempts


def background_child_failure_result(
    metadata: dict[str, Any],
    stdout_path: Path,
    stderr_path: Path,
    *,
    code: str,
    message: str,
    exit_code: int | None = None,
) -> dict[str, Any]:
    attempts = candidate_attempts_from_stderr(stderr_path)
    return envelope(
        ok=False,
        command=job_child_command(metadata),
        status=code,
        provider={"type": "henry-local-background-job"},
        error_obj={
            "code": code,
            "message": message,
            "exit_code": exit_code,
            "stderr_tail": tail_text(stderr_path),
        },
        metadata={
            "job_id": metadata.get("job_id"),
            "job_path": metadata.get("job_path") or str(stdout_path.parent.resolve()),
            "stdout": str(stdout_path),
            "stderr": str(stderr_path),
            "pid": metadata.get("pid"),
            "child_pid": metadata.get("child_pid"),
            "exit_code": exit_code,
            "candidate_attempts": attempts,
        },
    )


def job_effective_status(metadata: dict[str, Any], result: dict[str, Any] | None, running: bool = False) -> str:
    metadata_status = str(metadata.get("status") or "").lower()
    if metadata_status == "cancelled":
        return "cancelled"
    if result is not None:
        result_status = str(result.get("status") or "").lower()
        error_code = str((result.get("error") or {}).get("code") or "").lower()
        if result_status in {"cancelled", "job_cancelled"} or error_code == "job_cancelled":
            return "cancelled"
        return "completed" if result.get("ok") else "failed"
    if running:
        return "running"
    return metadata_status or "unknown"


def compact_attempts(result: dict[str, Any] | None, stderr_path: Path) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    if result is not None:
        metadata = result.get("metadata") or {}
        raw_attempts = metadata.get("candidate_attempts") or metadata.get("route_attempts") or []
        if isinstance(raw_attempts, list):
            attempts.extend(item for item in raw_attempts if isinstance(item, dict))
    if not attempts:
        attempts = candidate_attempts_from_stderr(stderr_path)
    compacted: list[dict[str, Any]] = []
    for item in attempts:
        error_data = item.get("error") if isinstance(item.get("error"), dict) else {}
        compacted.append(redact({
            "route": item.get("route"),
            "status": item.get("status"),
            "error_code": item.get("error_code") or error_data.get("code"),
            "request_id": item.get("request_id"),
            "latency_ms": item.get("latency_ms"),
            "auth_source": item.get("auth_source"),
            "auth_shape": item.get("auth_shape"),
            "header_names": item.get("header_names"),
            "query_names": item.get("query_names"),
            "provider_family": item.get("provider_family"),
            "adaptive_reason": item.get("adaptive_reason"),
            "base_url_source": item.get("base_url_source"),
            "endpoint": item.get("endpoint"),
        }))
    return compacted


def diagnosis_category(status: str, result: dict[str, Any] | None, attempts: list[dict[str, Any]]) -> str:
    if status in {"completed", "running", "cancelled"}:
        return status
    if result is not None:
        result_status = str(result.get("status") or "").lower()
        error_data = result.get("error") or {}
        if result_status in {"child_no_result", "child_invalid_json", "write_error", "no_image_result", "job_cancelled"}:
            return "cancelled" if result_status == "job_cancelled" else result_status
        error_code = str(error_data.get("code") or "").lower()
        if error_code in {"child_no_result", "child_invalid_json", "write_error", "no_image_result", "job_cancelled"}:
            return "cancelled" if error_code == "job_cancelled" else error_code
        category = str(error_data.get("category") or classify_api_failure(error_data)).lower()
        if category and category != "api_error":
            return category
    if attempts:
        last = attempts[-1]
        error_code = str(last.get("error_code") or "").lower()
        status_code = last.get("status")
        if error_code or status_code is not None:
            return classify_api_failure({"status": status_code, "code": error_code, "message": error_code})
    if status == "failed":
        return "unknown"
    return status or "unknown"


def diagnosis_next_action(category: str) -> str:
    actions = {
        "completed": "No action needed. Review generated outputs and manifest.",
        "running": "Keep polling with job-status --watch, or use job-cancel --dry-run before cancelling.",
        "cancelled": "Job was cancelled. Start a new background job only if the route and prompt are still appropriate.",
        "missing_credentials": "Configure an authorized local API key or Codex auth source; do not paste secrets in chat.",
        "invalid_credentials": "Stop and check the selected auth source; do not fallback to another paid provider silently.",
        "content_policy": "Revise the prompt to satisfy policy; do not route/provider-fallback.",
        "quota_exceeded": "Stop or choose an explicitly authorized provider with available quota.",
        "rate_limited": "Wait and retry later, or choose an explicitly authorized provider; do not broad-fallback.",
        "bad_parameter": "Adjust model, size, quality, background, or explicitly try --images-compat minimal when only payload fields are rejected.",
        "timeout": "Retry as a background job with a higher --timeout if the same route is still appropriate.",
        "network_error": "Check local network/proxy/provider reachability without editing global proxy or secrets.",
        "server_error": "Retry later or use an explicitly authorized fallback route/provider.",
        "unsupported_router": "Use --route auto, the Image API route, or return a prompt package.",
        "no_image_result": "Try --route auto or Image API fallback; if unavailable, return a prompt package.",
        "child_no_result": "Inspect stderr_tail and candidate attempts; retry with --background-job only if the route is still appropriate.",
        "child_invalid_json": "Inspect stderr_tail; treat as provider/runner transport failure.",
        "write_error": "Check the output path, permissions, and --force behavior.",
        "cancel_failed": "Inspect cancel_attempts and terminate only the exact recorded PID manually if you trust it.",
        "not_running": "No active recorded PID was found. Use job-diagnose to inspect the final state.",
    }
    return actions.get(category, "Inspect stderr_tail, candidate attempts, and the selected route/auth source before retrying.")


def diagnosis_summary(category: str, status: str, result: dict[str, Any] | None) -> str:
    if category == "completed":
        return "Job completed successfully."
    if category == "running":
        return "Job is still running."
    if category == "cancelled":
        return "Job was cancelled."
    error_data = (result or {}).get("error") or {}
    code = error_data.get("code") or category
    message = error_data.get("message") or f"Job status is {status}."
    return f"Blocker: {category} ({code}). {message}"


def diagnosis_evidence(
    *,
    status: str,
    result: dict[str, Any] | None,
    metadata: dict[str, Any],
    attempts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    if result is not None:
        error_data = result.get("error") or {}
        evidence.append({
            "job_status": status,
            "result_status": result.get("status"),
            "error_code": error_data.get("code"),
            "error_category": error_data.get("category"),
            "request_id": result.get("request_id"),
        })
    else:
        evidence.append({"job_status": status, "metadata_status": metadata.get("status")})
    for attempt in attempts:
        evidence.append({
            "route": attempt.get("route"),
            "status": attempt.get("status"),
            "error_code": attempt.get("error_code"),
            "request_id": attempt.get("request_id"),
            "latency_ms": attempt.get("latency_ms"),
            "auth_source": attempt.get("auth_source"),
            "auth_shape": attempt.get("auth_shape"),
            "header_names": attempt.get("header_names"),
            "query_names": attempt.get("query_names"),
            "provider_family": attempt.get("provider_family"),
            "adaptive_reason": attempt.get("adaptive_reason"),
            "base_url_source": attempt.get("base_url_source"),
        })
    return [redact(item) for item in evidence]


def job_files(job_file: Path, metadata: dict[str, Any], stdout_path: Path, stderr_path: Path, result: dict[str, Any] | None) -> dict[str, Any]:
    files: dict[str, Any] = {
        "job_json": str(job_file),
        "stdout_json": str(stdout_path),
        "stderr_jsonl": str(stderr_path),
    }
    if metadata.get("out"):
        files["out"] = metadata.get("out")
    manifests: list[str] = []
    for output in (result or {}).get("outputs", []):
        if isinstance(output, dict):
            if output.get("path"):
                files.setdefault("outputs", []).append(output.get("path"))
            if output.get("manifest"):
                manifests.append(output.get("manifest"))
    if manifests:
        files["manifests"] = manifests
    return redact(files)


def build_job_diagnosis(job_file: Path, *, tail_lines: int = 80, status_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    metadata = read_json_file(job_file) or {}
    job_dir = job_file.parent
    stdout_path = Path(metadata.get("stdout") or job_dir / "stdout.json")
    stderr_path = Path(metadata.get("stderr") or job_dir / "stderr.jsonl")
    result = read_json_file(stdout_path)
    if status_payload and status_payload.get("outputs"):
        result = (status_payload["outputs"][0] or {}).get("result") or result
    running = bool((status_payload or {}).get("metadata", {}).get("running")) if status_payload else pid_running(metadata.get("pid"))
    status = str((status_payload or {}).get("status") or job_effective_status(metadata, result, running))
    attempts = compact_attempts(result, stderr_path)
    category = diagnosis_category(status, result, attempts)
    return redact({
        "summary": diagnosis_summary(category, status, result),
        "category": category,
        "next_action": diagnosis_next_action(category),
        "evidence": diagnosis_evidence(status=status, result=result, metadata=metadata, attempts=attempts),
        "files": job_files(job_file, metadata, stdout_path, stderr_path, result),
        "attempts": attempts,
        "stderr_tail": tail_text(stderr_path, tail_lines),
    })


def render_diagnosis_human(diagnosis: dict[str, Any]) -> str:
    lines = [
        f"Blocker: {diagnosis.get('category')}",
        f"Summary: {diagnosis.get('summary')}",
        f"Next action: {diagnosis.get('next_action')}",
        "",
        "Evidence:",
    ]
    for item in diagnosis.get("evidence") or []:
        parts = [f"{key}={value}" for key, value in item.items() if value not in (None, "")]
        if parts:
            lines.append("- " + ", ".join(parts))
    lines.append("")
    lines.append("Files:")
    for key, value in (diagnosis.get("files") or {}).items():
        lines.append(f"- {key}: {value}")
    attempts = diagnosis.get("attempts") or []
    if attempts:
        lines.append("")
        lines.append("Attempts:")
        for item in attempts:
            parts = [f"{key}={value}" for key, value in item.items() if value not in (None, "")]
            lines.append("- " + ", ".join(parts))
    stderr_tail = diagnosis.get("stderr_tail") or []
    if stderr_tail:
        lines.append("")
        lines.append("stderr_tail:")
        lines.extend(f"- {line}" for line in stderr_tail[-10:])
    return str(redact("\n".join(lines)))


def emit_human(text: str, ok: bool = True) -> int:
    try:
        print(redact(text))
    except UnicodeEncodeError:
        sys.stdout.buffer.write((str(redact(text)) + "\n").encode("utf-8", errors="replace"))
    return 0 if ok else 1


def pid_running(pid: int | None) -> bool:
    if not pid or pid < 1:
        return False
    if os.name == "nt":
        try:
            import ctypes  # noqa: PLC0415

            kernel32 = ctypes.windll.kernel32
            synchronize = 0x00100000
            wait_timeout = 0x00000102
            handle = kernel32.OpenProcess(synchronize, False, int(pid))
            if not handle:
                return False
            try:
                return kernel32.WaitForSingleObject(handle, 0) == wait_timeout
            finally:
                kernel32.CloseHandle(handle)
        except Exception:  # noqa: BLE001
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def terminate_pid(pid: int) -> dict[str, Any]:
    if pid < 1:
        return {"pid": pid, "ok": False, "message": "invalid pid", "alive_after": False}
    if not pid_running(pid):
        return {"pid": pid, "ok": True, "message": "not running", "alive_after": False}
    try:
        if os.name == "nt":
            proc = subprocess.run(
                ["taskkill", "/PID", str(pid)],
                text=True,
                capture_output=True,
                timeout=10,
            )
            time.sleep(0.5)
            alive_after = pid_running(pid)
            return {
                "pid": pid,
                "ok": proc.returncode == 0 and not alive_after,
                "message": (proc.stdout or proc.stderr or "").strip() or f"taskkill exit {proc.returncode}",
                "alive_after": alive_after,
            }
        os.kill(pid, signal.SIGTERM)
        time.sleep(1.0)
        alive_after = pid_running(pid)
        return {"pid": pid, "ok": not alive_after, "message": "SIGTERM sent", "alive_after": alive_after}
    except Exception as exc:  # noqa: BLE001
        return {"pid": pid, "ok": False, "message": str(exc), "alive_after": pid_running(pid)}


def recorded_job_pids(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    seen: set[int] = set()
    items: list[dict[str, Any]] = []
    for field in ("child_pid", "runner_pid", "pid"):
        raw = metadata.get(field)
        if raw is None:
            continue
        try:
            pid = int(raw)
        except (TypeError, ValueError):
            continue
        if pid < 1 or pid in seen:
            continue
        seen.add(pid)
        items.append({"field": field, "pid": pid, "running": pid_running(pid)})
    return items


def job_cancelled_result(metadata: dict[str, Any], stdout_path: Path, stderr_path: Path, cancel_attempts: list[dict[str, Any]], reason: str | None) -> dict[str, Any]:
    return envelope(
        ok=False,
        command=job_child_command(metadata),
        status="job_cancelled",
        provider={"type": "henry-local-background-job"},
        error_obj={"code": "job_cancelled", "message": "Background job was cancelled.", "reason": reason},
        metadata={
            "job_id": metadata.get("job_id"),
            "job_path": metadata.get("job_path") or str(stdout_path.parent.resolve()),
            "stdout": str(stdout_path),
            "stderr": str(stderr_path),
            "cancel_attempts": cancel_attempts,
            "cancel_reason": reason,
        },
    )


def child_argv_without_background() -> list[str]:
    args: list[str] = []
    skip_next = False
    for item in sys.argv[1:]:
        if skip_next:
            skip_next = False
            continue
        if item == "--background-job":
            continue
        if item.startswith("--background-job="):
            continue
        args.append(item)
    return args


def start_background_job(command_name: str, args: argparse.Namespace) -> dict[str, Any]:
    current_job_id = job_id()
    root = job_root(getattr(args, "jobs_dir", None))
    path = root / current_job_id
    path.mkdir(parents=True, exist_ok=False)
    stdout_path = path / "stdout.json"
    stderr_path = path / "stderr.jsonl"
    result_path = stdout_path
    job_path = path / "job.json"
    child_args = child_argv_without_background()
    child_command = [sys.executable, str(Path(__file__).resolve()), *child_args]
    runner_command = [sys.executable, str(Path(__file__).resolve()), "__job-runner", "--job-path", str(job_path.resolve())]
    metadata = {
        "job_id": current_job_id,
        "status": "starting",
        "command": f"henry.job.{command_name}",
        "child_command": child_command,
        "runner_command": runner_command,
        "cwd": os.getcwd(),
        "created_at": now_iso(),
        "pid": None,
        "runner_pid": None,
        "child_pid": None,
        "out": getattr(args, "out", None),
        "job_path": str(path.resolve()),
        "stdout": str(stdout_path.resolve()),
        "stderr": str(stderr_path.resolve()),
        "result": str(result_path.resolve()),
    }
    write_json_file(job_path, metadata)
    stdout_path.write_text("", encoding="utf-8")
    stderr_path.write_text("", encoding="utf-8")
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    process = subprocess.Popen(
        runner_command,
        cwd=os.getcwd(),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        close_fds=os.name != "nt",
        creationflags=creationflags,
    )
    metadata["status"] = "running"
    metadata["pid"] = process.pid
    metadata["runner_pid"] = process.pid
    metadata["started_at"] = now_iso()
    current_metadata = read_json_file(job_path) or {}
    if current_metadata.get("status") in FINAL_JOB_STATUSES:
        metadata = {**current_metadata, "pid": process.pid, "runner_pid": process.pid}
    else:
        metadata = {
            **metadata,
            **current_metadata,
            "status": "running",
            "pid": process.pid,
            "runner_pid": process.pid,
            "started_at": metadata["started_at"],
        }
    write_json_file(job_path, metadata)
    return envelope(
        ok=True,
        command="henry.job.start",
        status="running",
        provider={"type": "henry-local-background-job"},
        outputs=[
            {
                "type": "henry_job",
                "job_id": current_job_id,
                "job_path": str(path.resolve()),
                "pid": process.pid,
                "stdout": str(stdout_path.resolve()),
                "stderr": str(stderr_path.resolve()),
                "result": str(result_path.resolve()),
                "out": getattr(args, "out", None),
            }
        ],
        metadata=metadata,
    )


def command_job_runner(args: argparse.Namespace) -> int:
    job_file = Path(args.job_path)
    metadata = read_json_file(job_file) or {}
    job_dir = job_file.parent
    stdout_path = Path(metadata.get("stdout") or job_dir / "stdout.json")
    stderr_path = Path(metadata.get("stderr") or job_dir / "stderr.jsonl")
    if str(metadata.get("status") or "").lower() == "cancelled":
        append_job_event(stderr_path, "job_runner_finish", status="cancelled", exit_code=metadata.get("exit_code"))
        update_job_json(job_file, {"status": "cancelled", "last_heartbeat": now_iso()})
        return 1
    child_command = metadata.get("child_command")
    if not isinstance(child_command, list) or not child_command:
        result = background_child_failure_result(
            metadata,
            stdout_path,
            stderr_path,
            code="job_invalid",
            message="Background job metadata is missing child_command.",
        )
        write_json_file(stdout_path, result)
        update_job_json(job_file, {"status": "failed", "finished_at": now_iso(), "exit_code": None})
        return 1

    append_job_event(stderr_path, "job_runner_start", runner_pid=os.getpid())
    update_job_json(job_file, {"status": "running", "runner_pid": os.getpid(), "pid": os.getpid(), "runner_started_at": now_iso(), "last_heartbeat": now_iso()})
    child_stdout_path = stdout_path.with_name(f"{stdout_path.name}.{uuid.uuid4().hex}.child.tmp")
    stdout_handle = child_stdout_path.open("w", encoding="utf-8")
    stderr_handle = stderr_path.open("a", encoding="utf-8")
    exit_code: int | None = None
    try:
        env = os.environ.copy()
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("PYTHONUTF8", "1")
        process = subprocess.Popen(
            child_command,
            cwd=str(metadata.get("cwd") or os.getcwd()),
            env=env,
            stdout=stdout_handle,
            stderr=stderr_handle,
            stdin=subprocess.DEVNULL,
            close_fds=os.name != "nt",
        )
        update_job_json(job_file, {"status": "running", "child_pid": process.pid, "child_started_at": now_iso(), "last_heartbeat": now_iso()})
        exit_code = process.wait()
        update_job_json(job_file, {"last_heartbeat": now_iso()})
    except Exception as exc:  # noqa: BLE001
        exit_code = 1
        append_job_event(stderr_path, "job_runner_error", message=str(exc))
    finally:
        stdout_handle.close()
        stderr_handle.close()

    latest_metadata = read_json_file(job_file) or metadata
    if str(latest_metadata.get("status") or "").lower() == "cancelled":
        if child_stdout_path.exists():
            try:
                child_stdout_path.unlink()
            except OSError:
                pass
        update_job_json(job_file, {"status": "cancelled", "exit_code": exit_code, "last_heartbeat": now_iso()})
        append_job_event(stderr_path, "job_runner_finish", status="cancelled", exit_code=exit_code)
        return 1

    result = read_json_file(child_stdout_path)
    if result is not None:
        os.replace(child_stdout_path, stdout_path)
    if result is None:
        code = "child_no_result" if not child_stdout_path.exists() or child_stdout_path.stat().st_size == 0 else "child_invalid_json"
        message = (
            "Background child exited without writing a CLI JSON envelope."
            if code == "child_no_result"
            else "Background child wrote stdout.json, but it was not valid JSON."
        )
        result = background_child_failure_result(
            metadata,
            stdout_path,
            stderr_path,
            code=code,
            message=message,
            exit_code=exit_code,
        )
        write_json_file(stdout_path, result)
        if child_stdout_path.exists():
            try:
                child_stdout_path.unlink()
            except OSError:
                pass

    status = "completed" if result.get("ok") else "failed"
    update_job_json(job_file, {"status": status, "exit_code": exit_code, "finished_at": now_iso(), "last_heartbeat": now_iso()})
    append_job_event(stderr_path, "job_runner_finish", status=status, exit_code=exit_code)
    return 0 if status == "completed" else 1


def job_status_payload(args: argparse.Namespace) -> dict[str, Any]:
    path = resolve_job_path(args.job, args.jobs_dir)
    job_file = path / "job.json" if path.is_dir() else path
    if not job_file.exists():
        return envelope(
            ok=False,
            command="henry.job.status",
            status="not_found",
            provider={"type": "henry-local-background-job"},
            error_obj={"code": "not_found", "message": f"Job not found: {args.job}"},
            metadata={"job": args.job, "resolved_path": str(job_file)},
        )
    metadata = read_json_file(job_file) or {}
    job_dir = job_file.parent
    stdout_path = Path(metadata.get("stdout") or job_dir / "stdout.json")
    stderr_path = Path(metadata.get("stderr") or job_dir / "stderr.jsonl")
    result = read_json_file(stdout_path)
    running = pid_running(metadata.get("pid"))
    error_obj = None
    metadata_status = str(metadata.get("status") or "").lower()
    if metadata_status == "cancelled":
        status = "cancelled"
        if result is not None:
            error_obj = result.get("error")
    elif metadata_status == "cancel_failed":
        status = "cancel_failed"
        error_obj = {"code": "cancel_failed", "message": "One or more recorded PIDs could not be terminated conservatively."}
    elif result is not None:
        status = job_effective_status(metadata, result, running)
        if status in {"failed", "cancelled"}:
            error_obj = result.get("error")
    elif running:
        status = "running"
    else:
        started_raw = metadata.get("started_at") or metadata.get("created_at")
        try:
            started_at = datetime.fromisoformat(started_raw) if started_raw else None
        except ValueError:
            started_at = None
        age_seconds = (datetime.now(timezone.utc) - started_at).total_seconds() if started_at else None
        status = "running" if age_seconds is not None and age_seconds < 10 else "failed"
    if result is None and status == "failed":
        result = background_child_failure_result(
            metadata,
            stdout_path,
            stderr_path,
            code="child_no_result" if not stdout_path.exists() or stdout_path.stat().st_size == 0 else "child_invalid_json",
            message=(
                "Background child exited without writing a CLI JSON envelope."
                if not stdout_path.exists() or stdout_path.stat().st_size == 0
                else "Background child wrote stdout.json, but it was not valid JSON."
            ),
            exit_code=metadata.get("exit_code"),
        )
        error_obj = result.get("error")
        if not stdout_path.exists() or stdout_path.stat().st_size == 0:
            write_json_file(stdout_path, result)
    if status in FINAL_JOB_STATUSES and metadata.get("status") != status:
        metadata = update_job_json(job_file, {"status": status, "observed_final_at": now_iso()})
    output = {
        "type": "henry_job_status",
        "job_id": metadata.get("job_id") or job_dir.name,
        "job_path": str(job_dir.resolve()),
        "pid": metadata.get("pid"),
        "running": running,
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
        "stderr_tail": tail_text(stderr_path),
        "result": result,
    }
    if getattr(args, "diagnose", False):
        output["diagnosis"] = build_job_diagnosis(job_file, tail_lines=int(getattr(args, "tail_lines", 80)), status_payload={
            "status": status,
            "outputs": [output],
            "metadata": {**metadata, "running": running},
        })
    return envelope(
        ok=True,
        command="henry.job.status",
        status=status,
        provider={"type": "henry-local-background-job"},
        outputs=[output],
        error_obj=error_obj,
        metadata={**metadata, "observed_at": now_iso(), "running": running},
    )


def command_job_status(args: argparse.Namespace) -> int:
    while True:
        payload = job_status_payload(args)
        if not getattr(args, "watch", False) or payload.get("status") in FINAL_JOB_STATUSES | {"not_found", "cancel_failed"}:
            if getattr(args, "format", "json") == "human":
                output = (payload.get("outputs") or [{}])[0]
                diagnosis = output.get("diagnosis")
                if diagnosis is None and payload.get("status") != "not_found":
                    job_file = Path(output.get("job_path", "")) / "job.json"
                    if job_file.exists():
                        diagnosis = build_job_diagnosis(job_file, tail_lines=int(getattr(args, "tail_lines", 80)), status_payload=payload)
                if diagnosis is not None:
                    return emit_human(render_diagnosis_human(diagnosis), ok=True)
                return emit_human(f"Blocker: {payload.get('status')}\nNext action: {(payload.get('error') or {}).get('message') or 'Inspect job metadata.'}", ok=bool(payload.get("ok")))
            return emit_with_workflow(
                payload,
                args=args,
                command="henry.job.status",
                out=str(resolve_job_path(args.job, args.jobs_dir)),
                source_output=str(resolve_job_path(args.job, args.jobs_dir)),
                persist_on_success=False,
            )
        time.sleep(max(float(getattr(args, "interval", 2.0)), 0.01))


def command_job_diagnose(args: argparse.Namespace) -> int:
    path = resolve_job_path(args.job, args.jobs_dir)
    job_file = path / "job.json" if path.is_dir() else path
    if not job_file.exists():
        payload = envelope(
            ok=False,
            command="henry.job.diagnose",
            status="not_found",
            provider={"type": "henry-local-background-job"},
            error_obj={"code": "not_found", "message": f"Job not found: {args.job}"},
            metadata={"job": args.job, "resolved_path": str(job_file)},
        )
        if getattr(args, "format", "human") == "human":
            return emit_human(f"Blocker: not_found\nNext action: Check the job id or --jobs-dir.\nEvidence: {job_file}", ok=False)
        return emit_with_workflow(
            payload,
            args=args,
            command="henry.job.diagnose",
            out=str(job_file),
            source_output=str(job_file),
            persist_on_success=False,
        )
    diagnosis = build_job_diagnosis(job_file, tail_lines=int(getattr(args, "tail_lines", 80)))
    if getattr(args, "format", "human") == "human":
        return emit_human(render_diagnosis_human(diagnosis), ok=True)
    return emit_with_workflow(
        envelope(
            ok=True,
            command="henry.job.diagnose",
            status=diagnosis.get("category") or "unknown",
            provider={"type": "henry-local-background-job"},
            outputs=[{"type": "henry_job_diagnosis", "diagnosis": diagnosis}],
            metadata={"job": args.job, "observed_at": now_iso()},
        ),
        args=args,
        command="henry.job.diagnose",
        out=str(job_file),
        source_output=str(job_file),
        persist_on_success=False,
    )


def command_job_cancel(args: argparse.Namespace) -> int:
    path = resolve_job_path(args.job, args.jobs_dir)
    job_file = path / "job.json" if path.is_dir() else path
    if not job_file.exists():
        payload = envelope(
            ok=False,
            command="henry.job.cancel",
            status="not_found",
            provider={"type": "henry-local-background-job"},
            error_obj={"code": "not_found", "message": f"Job not found: {args.job}"},
            metadata={"job": args.job, "resolved_path": str(job_file)},
        )
        if getattr(args, "format", "json") == "human":
            return emit_human(f"Blocker: not_found\nNext action: Check the job id or --jobs-dir.\nEvidence: {job_file}", ok=False)
        return emit(payload)
    metadata = read_json_file(job_file) or {}
    job_dir = job_file.parent
    stdout_path = Path(metadata.get("stdout") or job_dir / "stdout.json")
    stderr_path = Path(metadata.get("stderr") or job_dir / "stderr.jsonl")
    result = read_json_file(stdout_path)
    running = pid_running(metadata.get("pid"))
    status = job_effective_status(metadata, result, running)
    cancel_plan = recorded_job_pids(metadata)
    if status in FINAL_JOB_STATUSES:
        payload = envelope(
            ok=True,
            command="henry.job.cancel",
            status="already_final",
            provider={"type": "henry-local-background-job"},
            outputs=[{"type": "henry_job_cancel", "job_id": metadata.get("job_id") or job_dir.name, "status": status, "cancel_plan": cancel_plan}],
            metadata={"job_path": str(job_dir.resolve()), "observed_at": now_iso()},
        )
        if getattr(args, "format", "json") == "human":
            return emit_human(f"Blocker: already_final\nSummary: Job is already {status}.\nNext action: Use job-diagnose if you need details.\nEvidence: {job_dir}", ok=True)
        return emit(payload)
    if getattr(args, "dry_run", False):
        payload = envelope(
            ok=True,
            command="henry.job.cancel",
            status="dry_run",
            provider={"type": "henry-local-background-job"},
            outputs=[{"type": "henry_job_cancel", "job_id": metadata.get("job_id") or job_dir.name, "cancel_plan": cancel_plan}],
            metadata={"job_path": str(job_dir.resolve()), "dry_run": True, "observed_at": now_iso()},
        )
        if getattr(args, "format", "json") == "human":
            return emit_human("Blocker: dry_run\nNext action: Run without --dry-run to cancel these exact recorded PIDs.\nEvidence: " + json.dumps(redact(cancel_plan), ensure_ascii=False), ok=True)
        return emit(payload)
    active_plan = [item for item in cancel_plan if item.get("running")]
    if not active_plan:
        payload = envelope(
            ok=False,
            command="henry.job.cancel",
            status="not_running",
            provider={"type": "henry-local-background-job"},
            outputs=[{"type": "henry_job_cancel", "job_id": metadata.get("job_id") or job_dir.name, "cancel_plan": cancel_plan}],
            error_obj={"code": "not_running", "message": "No active recorded PID was found for this job."},
            metadata={"job_path": str(job_dir.resolve()), "observed_at": now_iso()},
        )
        if getattr(args, "format", "json") == "human":
            return emit_human("Blocker: not_running\nNext action: Use job-diagnose to inspect the final state.\nEvidence: " + str(job_dir), ok=False)
        return emit(payload)
    append_job_event(stderr_path, "job_cancel_requested", reason=getattr(args, "reason", None), cancel_plan=active_plan)
    cancel_attempts = [terminate_pid(int(item["pid"])) | {"field": item.get("field")} for item in active_plan]
    success = all(item.get("ok") and not item.get("alive_after") for item in cancel_attempts)
    append_job_event(stderr_path, "job_cancel_finish", status="cancelled" if success else "cancel_failed", cancel_attempts=cancel_attempts)
    if success:
        updates = {
            "status": "cancelled",
            "cancelled_at": now_iso(),
            "cancel_reason": getattr(args, "reason", None),
            "cancel_attempts": cancel_attempts,
            "finished_at": now_iso(),
        }
        metadata = update_job_json(job_file, updates)
        if read_json_file(stdout_path) is None:
            write_json_file(stdout_path, job_cancelled_result(metadata, stdout_path, stderr_path, cancel_attempts, getattr(args, "reason", None)))
        payload = envelope(
            ok=True,
            command="henry.job.cancel",
            status="cancelled",
            provider={"type": "henry-local-background-job"},
            outputs=[{"type": "henry_job_cancel", "job_id": metadata.get("job_id") or job_dir.name, "cancel_attempts": cancel_attempts}],
            metadata={"job_path": str(job_dir.resolve()), "cancelled_at": updates["cancelled_at"]},
        )
        if getattr(args, "format", "json") == "human":
            return emit_human("Blocker: cancelled\nSummary: Job cancellation completed.\nNext action: Start a new background job only if needed.\nEvidence: " + str(job_dir), ok=True)
        return emit(payload)
    metadata = update_job_json(job_file, {"status": "cancel_failed", "cancel_attempts": cancel_attempts, "cancel_failed_at": now_iso(), "cancel_reason": getattr(args, "reason", None)})
    payload = envelope(
        ok=False,
        command="henry.job.cancel",
        status="cancel_failed",
        provider={"type": "henry-local-background-job"},
        outputs=[{"type": "henry_job_cancel", "job_id": metadata.get("job_id") or job_dir.name, "cancel_attempts": cancel_attempts}],
        error_obj={"code": "cancel_failed", "message": "One or more recorded PIDs could not be terminated conservatively."},
        metadata={"job_path": str(job_dir.resolve()), "observed_at": now_iso()},
    )
    if getattr(args, "format", "json") == "human":
        return emit_human("Blocker: cancel_failed\nNext action: Inspect cancel_attempts; do not broaden termination automatically.\nEvidence: " + json.dumps(redact(cancel_attempts), ensure_ascii=False), ok=False)
    return emit(payload)


def job_summary(job_dir: Path, jobs_dir: Path) -> dict[str, Any] | None:
    job_file = job_dir / "job.json"
    metadata = read_json_file(job_file)
    if metadata is None:
        return None
    stdout_path = Path(metadata.get("stdout") or job_dir / "stdout.json")
    result = read_json_file(stdout_path)
    status = metadata.get("status")
    if result is not None:
        status = job_effective_status(metadata, result)
    return {
        "job_id": metadata.get("job_id") or job_dir.name,
        "status": status,
        "job_path": str(job_dir.resolve()),
        "created_at": metadata.get("created_at"),
        "started_at": metadata.get("started_at"),
        "finished_at": metadata.get("finished_at"),
        "out": metadata.get("out"),
        "pid": metadata.get("pid"),
        "child_pid": metadata.get("child_pid"),
        "exit_code": metadata.get("exit_code"),
    }


def command_job_list(args: argparse.Namespace) -> int:
    root = job_root(args.jobs_dir)
    jobs: list[dict[str, Any]] = []
    if root.exists():
        for job_dir in sorted((p for p in root.iterdir() if p.is_dir()), reverse=True):
            summary = job_summary(job_dir, root)
            if summary is not None:
                jobs.append(summary)
    return emit(envelope(
        ok=True,
        command="henry.job.list",
        status="completed",
        provider={"type": "henry-local-background-job"},
        outputs=[{"type": "henry_job_list", "jobs": jobs}],
        metadata={"jobs_dir": str(root), "count": len(jobs)},
    ))


def command_job_cleanup(args: argparse.Namespace) -> int:
    try:
        older_than_seconds = parse_duration_seconds(args.older_than)
    except ValueError as exc:
        return emit(envelope(
            ok=False,
            command="henry.job.cleanup",
            status="validation_error",
            provider={"type": "henry-local-background-job"},
            error_obj={"code": "bad_duration", "message": str(exc)},
        ))
    root = job_root(args.jobs_dir)
    cutoff = datetime.now(timezone.utc).timestamp() - older_than_seconds
    removed: list[dict[str, Any]] = []
    if root.exists():
        root_resolved = root.resolve()
        for job_dir in sorted((p for p in root.iterdir() if p.is_dir())):
            summary = job_summary(job_dir, root)
            if summary is None:
                continue
            created_raw = summary.get("created_at")
            try:
                created_at = datetime.fromisoformat(created_raw).timestamp() if created_raw else job_dir.stat().st_mtime
            except (ValueError, OSError):
                created_at = job_dir.stat().st_mtime
            if created_at > cutoff:
                continue
            target = job_dir.resolve()
            if root_resolved not in target.parents:
                continue
            shutil.rmtree(target)
            removed.append({"job_id": summary.get("job_id"), "job_path": str(target)})
    return emit(envelope(
        ok=True,
        command="henry.job.cleanup",
        status="completed",
        provider={"type": "henry-local-background-job"},
        outputs=[{"type": "henry_job_cleanup", "removed": removed}],
        metadata={"jobs_dir": str(root), "removed_count": len(removed), "older_than": args.older_than},
    ))


def unsupported_responses_result(result: dict[str, Any]) -> bool:
    return core_routing.unsupported_responses_result(result, classify_api_failure)


def unsupported_images_payload_result(result: ApiResult) -> bool:
    return core_routing.unsupported_images_payload_result(result)


def legacy_should_try_next_candidate(result: dict[str, Any]) -> bool:
    return core_routing.legacy_should_try_next_candidate(result)


def should_try_next_candidate(result: dict[str, Any], args: argparse.Namespace | None = None) -> bool:
    return core_routing.should_try_next_candidate(result, args, classify_api_failure)


def summarize_attempt(result: dict[str, Any], base_url: str, base_url_source: str, route: str) -> dict[str, Any]:
    return core_routing.summarize_attempt(result, base_url, base_url_source, route)


def is_edit_command(command: str) -> bool:
    return core_routing.is_edit_command(command)


def image_provider_primary_failure_message(error_obj: dict[str, Any]) -> str:
    status = error_obj.get("status")
    message = str(error_obj.get("message") or "").lower()
    if status == 502:
        return "primary image relay upstream 502"
    if "image generation is not enabled" in message:
        return "primary image relay does not currently allow image_generation tool calls"
    if "unsupported" in message and "image" in message:
        return "primary image relay image_generation unsupported"
    return "primary image relay failed"


def image_provider_failure_user_message(result: dict[str, Any]) -> str:
    metadata = result.get("metadata") or {}
    notes = metadata.get("image_provider_health_notes") or []
    skipped = metadata.get("skipped_image_provider_candidates") or []
    attempts = metadata.get("candidate_attempts") or []
    active = metadata.get("active_image_model_provider_candidates") or metadata.get("image_provider_candidates_active") or []
    discovered_count = len(notes) if isinstance(notes, list) else 0
    skipped_count = len(skipped) if isinstance(skipped, list) else 0
    attempted_no_image = any(item.get("status") == "no_image_result" for item in attempts if isinstance(item, dict))
    verified_count = sum(
        1
        for item in notes
        if isinstance(item, dict) and item.get("image_generation_capability") == "verified"
    )
    lines = [
        "Henry Image 自动选路正常，但当前没有可用的真实图片生成 provider。",
        f"模型可见：{discovered_count} 个；当前可自动使用：{len(active) if isinstance(active, list) else 0} 个；已验证可生图：{verified_count} 个。",
    ]
    if attempted_no_image:
        lines.append("本次上游返回了成功响应，但没有返回图片字节；这通常表示 AiMaMi 暴露了 gpt-image-2 名称，但该上游组没有启用真实图片生成。")
    elif skipped_count:
        lines.append(f"{skipped_count} 个 provider 因最近失败正在冷却，避免反复重试浪费时间。")
    error_obj = result.get("error") or {}
    if error_obj.get("message"):
        lines.append(f"当前原因：{error_obj.get('message')}")
    lines.append("下一步：稍后运行 `probe-image-providers --live --candidate-policy all --format human` 重测；如果上游恢复，会自动写入 verified 并恢复 auto 出图。")
    return "\n".join(lines)


def attach_image_provider_failure_summary(result: dict[str, Any]) -> None:
    if result.get("ok"):
        return
    metadata = result.setdefault("metadata", {})
    primary = metadata.get("primary_image_provider")
    skipped = metadata.get("skipped_image_provider_candidates") or []
    attempts = metadata.get("candidate_attempts") or []
    primary_attempt = None
    if primary:
        for attempt in attempts:
            if attempt.get("base_url_source") == primary:
                primary_attempt = attempt
                break
    summary: dict[str, Any] = {}
    if primary_attempt:
        err = primary_attempt.get("error") or {}
        summary["primary"] = {
            "base_url_source": primary,
            "status": primary_attempt.get("status"),
            "error_status": err.get("status"),
            "error_code": err.get("code"),
            "message": image_provider_primary_failure_message(err),
        }
    if skipped:
        summary["skipped_backups"] = [
            {
                "base_url_source": item.get("base_url_source"),
                "provider_id": item.get("provider_id"),
                "status": item.get("status"),
                "message": (
                    "image provider recently unsupported/unavailable"
                    if item.get("role") == "primary"
                    else "backup image relay recently unsupported/unavailable"
                ),
                "reason": item.get("reason"),
            }
            for item in skipped
        ]
    if summary:
        metadata["image_provider_summary"] = summary
    if metadata.get("image_model_provider_preferred") or metadata.get("image_provider_health_notes"):
        metadata["user_message"] = image_provider_failure_user_message(result)


def attach_attempt_metadata(result: dict[str, Any], attempts: list[dict[str, Any]]) -> None:
    metadata = result.setdefault("metadata", {})
    metadata["candidate_attempts"] = attempts
    metadata["route_attempts"] = [
        {
            "base_url_source": item.get("base_url_source"),
            "route": item.get("route"),
            "ok": item.get("ok"),
            "status": item.get("status"),
            "auth_source": item.get("auth_source"),
            "auth_shape": item.get("auth_shape"),
            "header_names": item.get("header_names"),
            "query_names": item.get("query_names"),
            "provider_family": item.get("provider_family"),
            "adaptive_reason": item.get("adaptive_reason"),
            "error": item.get("error"),
        }
        for item in attempts
    ]
    for output in result.get("outputs", []):
        if not isinstance(output, dict):
            continue
        manifest_path = output.get("manifest")
        if not manifest_path:
            continue
        path = Path(manifest_path)
        if not path.exists():
            continue
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        manifest_metadata = manifest.setdefault("metadata", {})
        manifest_metadata["candidate_attempts"] = attempts
        manifest_metadata["route_attempts"] = metadata["route_attempts"]
        path.write_text(json.dumps(redact(manifest), ensure_ascii=False, indent=2), encoding="utf-8")


def run_route_request(
    *,
    route: str,
    command: str,
    args: argparse.Namespace,
    payload: dict[str, Any] | None,
    prompt: str,
    out: str,
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base_url = normalize_base_url(args.base_url)
    base_url_source = getattr(args, "base_url_source", None)
    responses_model, responses_model_source = effective_responses_model(args, base_url_source)
    provider = provider_info(base_url, route)
    edit_command = is_edit_command(command)
    url = endpoint(base_url, "/responses" if route == "responses" else ("/images/edits" if edit_command else "/images/generations"))
    multipart_fields: list[tuple[str, str]] | None = None
    multipart_files: list[tuple[str, str, str, bytes]] | None = None
    try:
        if route == "responses":
            request_payload = dict(payload or {})
            request_payload["model"] = responses_model
            request_payload_summary = request_payload
            payload_kind = "json"
        elif edit_command:
            multipart_fields, multipart_files, request_payload_summary = build_images_edit_request(prompt, args)
            request_payload = None
            payload_kind = "multipart"
        else:
            request_payload = build_images_payload(prompt, args)
            request_payload_summary = request_payload
            payload_kind = "json"
    except Exception as exc:  # noqa: BLE001
        return envelope(
            ok=False,
            command=command,
            status="validation_error",
            provider=provider,
            error_obj={"message": str(exc)},
            metadata={
                "created_at": now_iso(),
                "codex_access": effective_codex_access_info(),
                "route": route,
                "base_url_source": base_url_source,
                "prompt": prompt,
                **(extra_metadata or {}),
            },
        )
    payload_mode = (
        "responses"
        if route == "responses"
        else ("images_edit_minimal" if edit_command and args.images_compat == "minimal" else "images_edit_openai" if edit_command else "minimal" if args.images_compat == "minimal" else "openai")
    )
    metadata = {
        "created_at": now_iso(),
        "codex_access": effective_codex_access_info(),
        "model": responses_model if route == "responses" else args.model,
        "model_source": responses_model_source if route == "responses" else getattr(args, "model_source", "cli_or_default"),
        "image_model": args.image_model,
        "size": args.size,
        "quality": args.quality,
        "output_format": args.output_format,
        "images_response_format": args.images_response_format,
        "images_compat": args.images_compat,
        "input_fidelity": args.input_fidelity,
        "payload_mode": payload_mode,
        "payload_kind": payload_kind,
        "n": args.n,
        "candidate_policy": getattr(args, "candidate_policy", "auto"),
        "background": args.background,
        "moderation": args.moderation,
        "route": route,
        "prompt": prompt,
        **(extra_metadata or {}),
    }
    profiles = auth_profiles(base_url, base_url_source, args.api_key_env, route)
    if getattr(args, "candidate_policy", "auto") == "strict":
        profiles = profiles[:1]
    auth_plan = [auth_profile_summary(profile) for profile in profiles]
    metadata["auth_source_set"] = [profile.source for profile in profiles]
    metadata["auth_shape_set"] = [profile.shape for profile in profiles]
    metadata["auth_plan"] = auth_plan
    metadata["provider_family"] = provider_family(base_url, base_url_source)
    if profiles:
        metadata.update(auth_profile_summary(profiles[0]))

    if args.dry_run:
        return envelope(
            ok=True,
            command=command,
            status="dry_run",
            provider=provider,
            metadata={
                **metadata,
                "url": url,
                "payload": redact(request_payload_summary),
                "out": out,
                "base_url_source": getattr(args, "base_url_source", None),
                "base_url_env_checked": base_url_env_candidates(),
                "api_key_env_checked": api_key_env_candidates(args.api_key_env),
                "auth_plan": auth_plan,
            },
        )
    if not profiles:
        return envelope(
            ok=False,
            command=command,
            status="missing_credentials",
            provider=provider,
            error_obj={"code": "missing_openai_api_key", "message": "No usable API authentication was found for this route. For Codex providers, ensure Codex auth is available or the provider allows no-auth local requests; otherwise set OPENAI_API_KEY, HENRY_IMAGE_API_KEY, another supported *_API_KEY env, or pass --api-key-env for this command. Do not paste secrets in chat."},
            metadata={
                **metadata,
                "base_url_source": base_url_source,
                "codex_access": effective_codex_access_info(),
                "api_key_env_checked": api_key_env_candidates(args.api_key_env),
                "auth_plan": auth_plan,
            },
        )
    auth_attempts: list[dict[str, Any]] = []
    result: ApiResult | None = None
    selected_auth_source: str | None = None
    selected_auth_value: str | None = None
    selected_profile: AuthProfile | None = None
    for profile in profiles:
        profile_summary = auth_profile_summary(profile)
        selected_auth_source = profile.source
        selected_auth_value = profile.value
        selected_profile = profile
        stderr_event(
            "request_start",
            command=command,
            route=route,
            endpoint=url,
            base_url_source=base_url_source,
            **profile_summary,
        )
        if payload_kind == "multipart":
            assert multipart_fields is not None and multipart_files is not None
            result = request_multipart(
                url,
                profile.value,
                multipart_fields,
                multipart_files,
                args.retries,
                args.timeout,
                auth_profile=profile,
            )
        else:
            assert request_payload is not None
            result = request_json(
                url,
                profile.value,
                request_payload,
                args.retries,
                args.timeout,
                auth_profile=profile,
            )
        stderr_event(
            "request_finish",
            command=command,
            route=route,
            endpoint=url,
            base_url_source=base_url_source,
            **profile_summary,
            ok=result.ok,
            status=result.status,
            error_code=(result.error or {}).get("code"),
            request_id=result.request_id,
            latency_ms=result.latency_ms,
        )
        auth_attempts.append({**profile_summary, "ok": result.ok, "status": result.status, "error": result.error})
        if result.ok or not should_try_next_api_key(result):
            break
        stderr_event(
            "api_key_fallback",
            from_auth_source=profile.source,
            from_auth_shape=profile.shape,
            reason=(result.error or {}).get("message"),
        )
    assert result is not None
    metadata["auth_source"] = selected_auth_source
    metadata["api_key_env"] = selected_auth_source
    metadata["base_url_source"] = base_url_source
    if selected_profile is not None:
        metadata.update(auth_profile_summary(selected_profile))
    if len(auth_attempts) > 1:
        metadata["auth_attempts"] = auth_attempts
        metadata["api_key_attempts"] = auth_attempts
    metadata["latency_ms"] = result.latency_ms
    if route == "images" and args.images_compat == "auto" and not result.ok and unsupported_images_payload_result(result):
        stderr_event("payload_fallback", route=route, from_mode="openai", to_mode="minimal", reason=(result.error or {}).get("message"))
        if edit_command:
            multipart_fields, multipart_files, request_payload_summary = build_images_edit_request(prompt, args, compat_mode="minimal")
            metadata["payload_mode"] = "images_edit_minimal"
            stderr_event(
                "request_start",
                command=command,
                route=route,
                endpoint=url,
                payload_mode="minimal",
                base_url_source=base_url_source,
                **(auth_profile_summary(selected_profile) if selected_profile is not None else {"auth_source": selected_auth_source}),
            )
            result = request_multipart(
                url,
                selected_auth_value,
                multipart_fields,
                multipart_files,
                args.retries,
                args.timeout,
                auth_profile=selected_profile,
            )
        else:
            request_payload = build_images_payload(prompt, args, compat_mode="minimal")
            metadata["payload_mode"] = "minimal"
            stderr_event(
                "request_start",
                command=command,
                route=route,
                endpoint=url,
                payload_mode="minimal",
                base_url_source=base_url_source,
                **(auth_profile_summary(selected_profile) if selected_profile is not None else {"auth_source": selected_auth_source}),
            )
            result = request_json(
                url,
                selected_auth_value,
                request_payload,
                args.retries,
                args.timeout,
                auth_profile=selected_profile,
            )
        stderr_event(
            "request_finish",
            command=command,
            route=route,
            endpoint=url,
            base_url_source=base_url_source,
            payload_mode=metadata.get("payload_mode"),
            **(auth_profile_summary(selected_profile) if selected_profile is not None else {"auth_source": selected_auth_source}),
            ok=result.ok,
            status=result.status,
            error_code=(result.error or {}).get("code"),
            request_id=result.request_id,
            latency_ms=result.latency_ms,
        )
        metadata["latency_ms"] = result.latency_ms
    if not result.ok or result.data is None:
        error_obj = failure_error_obj(result.error)
        return envelope(
            ok=False,
            command=command,
            status=error_obj.get("category") or "api_error",
            provider=provider,
            error_obj=error_obj,
            metadata=metadata,
            request_id=result.request_id,
        )
    url_images: list[str] = []
    if route == "responses":
        images = collect_response_images(result.data)
    else:
        images, url_images = collect_images_api_images(result.data)
    if not images:
        if url_images:
            try:
                raw_images = [download_image(item, args.timeout) for item in url_images]
                outputs = write_image_bytes(raw_images, out, args.output_format, args.force)
                manifest = {
                    "provider": provider,
                    "request_id": result.request_id or request_id_from_response(result.data),
                    "outputs": outputs,
                    "metadata": {**metadata, "image_urls": url_images},
                }
                manifest_path = write_manifest(outputs[0]["path"], manifest, args.force)
                outputs[0]["manifest"] = manifest_path
                return envelope(
                    ok=True,
                    command=command,
                    status="completed",
                    provider=provider,
                    outputs=outputs,
                    metadata=metadata,
                    request_id=result.request_id or request_id_from_response(result.data),
                )
            except Exception as exc:  # noqa: BLE001
                return envelope(
                    ok=False,
                    command=command,
                    status="write_error",
                    provider=provider,
                    error_obj={"code": "write_error", "message": str(exc)},
                    metadata=metadata,
                    request_id=result.request_id,
                )
        return envelope(
            ok=False,
            command=command,
            status="no_image_result",
            provider=provider,
            error_obj={"code": "no_image_result", "message": f"No image result found from {route} route. This route may not support image generation."},
            metadata={
                **metadata,
                "response_types": [item.get("type") for item in result.data.get("output", [])] if route == "responses" else [],
                "data_count": len(result.data.get("data", [])) if isinstance(result.data.get("data"), list) else None,
            },
            request_id=result.request_id or request_id_from_response(result.data),
        )
    try:
        outputs = write_images(images, out, args.output_format, args.force)
        manifest = {
            "provider": provider,
            "request_id": result.request_id or request_id_from_response(result.data),
            "outputs": outputs,
            "metadata": metadata,
        }
        manifest_path = write_manifest(outputs[0]["path"], manifest, args.force)
        outputs[0]["manifest"] = manifest_path
    except Exception as exc:  # noqa: BLE001
        return envelope(
            ok=False,
            command=command,
            status="write_error",
            provider=provider,
            error_obj={"code": "write_error", "message": str(exc)},
            metadata=metadata,
            request_id=result.request_id,
        )
    return envelope(
        ok=True,
        command=command,
        status="completed",
        provider=provider,
        outputs=outputs,
        metadata=metadata,
        request_id=result.request_id or request_id_from_response(result.data),
    )


def run_request(
    *,
    command: str,
    args: argparse.Namespace,
    payload: dict[str, Any],
    prompt: str,
    out: str,
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    route = getattr(args, "route", "responses")
    attempts: list[dict[str, Any]] = []
    routes = ["responses", "images"] if route == "auto" else [route]
    last_result: dict[str, Any] | None = None
    image_candidates = image_model_base_url_candidates(args)
    active_image_candidates = active_image_model_base_url_candidates(args)
    image_notes = image_provider_candidate_notes(image_candidates)
    request_extra_metadata = {
        **(extra_metadata or {}),
        "image_model_provider_candidates": image_candidates,
        "active_image_model_provider_candidates": active_image_candidates,
        "image_model_provider_preferred": bool(image_candidates),
        **image_notes,
    }

    policy_candidates = policy_base_url_candidates(args)
    if not policy_candidates and getattr(args, "dry_run", False):
        fallback_candidates = image_candidates or base_url_candidates(getattr(args, "base_url", None))
        policy_candidates = fallback_candidates[:1] if fallback_candidates else [(DEFAULT_BASE_URL, "default")]
    if not policy_candidates:
        provider_base_url = image_candidates[0][0] if image_candidates else DEFAULT_BASE_URL
        result = envelope(
            ok=False,
            command=command,
            status="image_provider_unavailable",
            provider=provider_info(provider_base_url, "responses" if route == "auto" else route),
            error_obj={
                "code": "image_provider_unavailable",
                "message": (
                    "Matching image providers were discovered, but all currently active candidates are "
                    "cooling down or marked unusable by Henry Image's capability cache. Use "
                    "probe-image-providers for diagnosis, or candidate-policy all only when deliberately "
                    "retesting skipped providers."
                ),
            },
            metadata={
                **request_extra_metadata,
                "created_at": now_iso(),
                "route": route,
                "candidate_policy": getattr(args, "candidate_policy", "auto"),
                "prompt": prompt,
                "image_model": getattr(args, "image_model", DEFAULT_IMAGE_MODEL),
                "image_provider_candidates_active": active_image_candidates,
            },
        )
        attach_image_provider_failure_summary(result)
        return result

    for candidate_index, (base_url, base_url_source) in enumerate(policy_candidates):
        candidate_args = clone_args(args, base_url=base_url, base_url_source=base_url_source)
        base_result: dict[str, Any] | None = None
        for route_name in routes:
            if route_name == "images" and route == "auto":
                if base_result is not None and not unsupported_responses_result(base_result):
                    break
                stderr_event(
                    "route_fallback",
                    from_route="responses",
                    to_route="images",
                    base_url_source=base_url_source,
                    reason=base_result.get("status") if base_result else None,
                )
            result = run_route_request(
                route=route_name,
                command=command,
                args=candidate_args,
                payload=payload if route_name == "responses" else None,
                prompt=prompt,
                out=out,
                extra_metadata=request_extra_metadata,
            )
            record_image_provider_attempt(base_url, base_url_source, route_name, result)
            if result.get("ok") and result.get("status") != "dry_run":
                result.setdefault("metadata", {})["image_generation_capability"] = "verified"
                result["metadata"]["image_provider_capability_cache"] = image_provider_health_cache()
            attempts.append(summarize_attempt(result, base_url, base_url_source, route_name))
            attach_attempt_metadata(result, attempts)
            last_result = result
            if route_name == "responses":
                base_result = result
            if result.get("ok"):
                return result
            if route_name == "responses" and route == "auto" and unsupported_responses_result(result):
                continue
            break

        has_next_candidate = candidate_index + 1 < len(policy_candidates)
        if last_result is not None and has_next_candidate and should_try_next_candidate(last_result, args):
            stderr_event(
                "base_url_fallback",
                from_base_url_source=base_url_source,
                reason=last_result.get("status"),
                candidate_policy=getattr(args, "candidate_policy", "auto"),
            )
            continue
        break

    assert last_result is not None
    attach_attempt_metadata(last_result, attempts)
    last_result.setdefault("metadata", {})["image_provider_capability_cache"] = image_provider_health_cache()
    refreshed_notes = image_provider_candidate_notes(image_candidates)
    for key in (
        "skipped_image_provider_candidates",
        "image_provider_health_notes",
        "image_provider_candidates_discovered",
        "image_provider_candidates_skipped",
        "image_generation_capability",
        "image_provider_selection_reason",
    ):
        last_result["metadata"][key] = refreshed_notes.get(key)
    attach_image_provider_failure_summary(last_result)
    return last_result


def command_probe(args: argparse.Namespace) -> int:
    base_candidates = policy_base_url_candidates(args)
    if not base_candidates:
        image_candidates = image_model_base_url_candidates(args)
        image_notes = image_provider_candidate_notes(image_candidates)
        return emit(envelope(
            ok=False,
            command="henry.probe",
            status="image_provider_unavailable",
            provider=provider_info(image_candidates[0][0] if image_candidates else DEFAULT_BASE_URL, args.route),
            error_obj={
                "code": "image_provider_unavailable",
                "message": "No active image provider candidate is currently recommended for auto mode. Use probe-image-providers for details, or candidate-policy all to deliberately retest skipped providers.",
            },
            metadata={
                "codex_access": effective_codex_access_info(),
                "live": args.live,
                "candidate_policy": getattr(args, "candidate_policy", "auto"),
                "image_model_provider_candidates": image_candidates,
                "active_image_model_provider_candidates": [],
                **image_notes,
            },
        ))
    base_url = base_candidates[0][0]
    base_url_source = base_candidates[0][1]
    provider = provider_info(base_url, args.route)
    profiles = auth_profiles(base_url, base_url_source, args.api_key_env, args.route)
    if getattr(args, "candidate_policy", "auto") == "strict":
        profiles = profiles[:1]
    auth_source = profiles[0].source if profiles else None
    api_key_env_set = [name for _, name in api_key_candidates(args.api_key_env)]
    base_url_env_set = [
        source
        for _, source in base_candidates
        if source not in {"cli", "default"} and not source.startswith("codex_config:")
    ]
    auth_plan = [auth_profile_summary(profile) for profile in profiles]
    metadata: dict[str, Any] = {
        "codex_access": effective_codex_access_info(),
        "api_key": "set" if profiles else "missing",
        "api_key_env": auth_source,
        "auth_source": auth_source,
        "auth_shape": profiles[0].shape if profiles else None,
        "header_names": list(profiles[0].headers.keys()) if profiles else [],
        "query_names": list(profiles[0].query.keys()) if profiles else [],
        "provider_family": provider_family(base_url, base_url_source),
        "adaptive_reason": profiles[0].adaptive_reason if profiles else None,
        "auth_source_set": [profile.source for profile in profiles],
        "auth_shape_set": [profile.shape for profile in profiles],
        "auth_plan": auth_plan,
        "api_key_env_checked": api_key_env_candidates(args.api_key_env),
        "api_key_env_set": api_key_env_set,
        "base_url_env_checked": base_url_env_candidates(),
        "base_url_env_set": base_url_env_set,
        "candidate_summary": [
            {
                "base_url_source": source,
                "base_url_host": parse.urlparse(url).netloc or url,
                "api_key_env_set": api_key_env_set,
                "auth_source_set": [profile.source for profile in auth_profiles(url, source, args.api_key_env, args.route)],
                "auth_shape_set": [profile.shape for profile in auth_profiles(url, source, args.api_key_env, args.route)],
                "auth_plan": [auth_profile_summary(profile) for profile in auth_profiles(url, source, args.api_key_env, args.route)],
                "routes": ["responses", "images"] if args.route == "auto" else [args.route],
            }
            for url, source in base_candidates
        ],
        "image_generation": "unverified",
        "live": args.live,
    }
    if not profiles:
        return emit(envelope(
            ok=False,
            command="henry.probe",
            status="missing_credentials",
            provider=provider,
            error_obj={"code": "missing_openai_api_key", "message": "No usable API authentication was found for this route. For Codex providers, ensure Codex auth is available or the provider allows no-auth local requests; otherwise set OPENAI_API_KEY, HENRY_IMAGE_API_KEY, another supported *_API_KEY env, or pass --api-key-env for this command. Do not paste secrets in chat."},
            metadata=metadata,
        ))
    if not args.live:
        metadata["image_generation"] = "unverified"
        metadata["note"] = "probe without --live checks environment only and does not spend image-generation quota."
        return emit(envelope(ok=True, command="henry.probe", status="environment_ready", provider=provider, metadata=metadata))
    prompt = "A tiny plain test image of a white square on a gray background, no text."
    payload = build_payload(prompt=prompt, args=args)
    result = run_request(command="henry.probe", args=args, payload=payload, prompt=prompt, out=args.out, extra_metadata={"live_probe": True})
    if result["ok"]:
        result["metadata"]["image_generation"] = "verified"
    return emit(result)


def provider_records_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    model_visible = sum(1 for item in records if item.get("model_visible"))
    verified = sum(
        1
        for item in records
        if item.get("responses_image_generation_verified") is True
        or item.get("images_generation_supported") is True
        or item.get("image_generation_capability") == "verified"
    )
    recommended = sum(1 for item in records if item.get("recommended_for_auto"))
    skipped = sum(1 for item in records if item.get("temporarily_unusable"))
    return {
        "total": len(records),
        "model_visible": model_visible,
        "verified": verified,
        "recommended_for_auto": recommended,
        "skipped": skipped,
    }


def render_provider_probe_human(payload: dict[str, Any]) -> str:
    outputs = payload.get("outputs") or []
    records = []
    if outputs and isinstance(outputs[0], dict):
        raw_records = outputs[0].get("providers")
        records = raw_records if isinstance(raw_records, list) else []
    summary = provider_records_summary(records)
    lines = [
        "Henry Image 图像通道状态",
        f"- 自动选路层：正常，会动态读取 Codex/AiMaMi 当前 provider，不依赖固定 relay id。",
        f"- 发现 provider：{summary['total']} 个",
        f"- 模型可见：{summary['model_visible']} 个",
        f"- 真实生图已验证：{summary['verified']} 个",
        f"- 当前 auto 推荐可用：{summary['recommended_for_auto']} 个",
        f"- 冷却/跳过：{summary['skipped']} 个",
    ]
    metadata = payload.get("metadata") or {}
    if not metadata.get("live"):
        lines.append("- 本次没有花额度：只读配置、AiMaMi state 和 Henry Image 缓存。")
    if records:
        lines.append("")
        lines.append("Provider 明细：")
        for item in records:
            cooldown = item.get("cooldown") if isinstance(item.get("cooldown"), dict) else {}
            remaining = cooldown.get("remaining_seconds")
            suffix = f"，剩余冷却 {format_duration(remaining)}" if item.get("temporarily_unusable") else ""
            cache = item.get("capability_cache") if isinstance(item.get("capability_cache"), dict) else {}
            reason = image_provider_cache_reason_zh(cache)
            lines.append(
                f"- {item.get('provider_id')}: "
                f"能力={item.get('image_generation_capability')}, "
                f"auto={'是' if item.get('recommended_for_auto') else '否'}, "
                f"原因={reason}{suffix}"
            )
    else:
        lines.append("")
        lines.append("没有发现 direct by-provider 图像候选；这通常表示 AiMaMi/Codex 当前没有把 gpt-image-2 图像 provider 暴露给 Henry Image。")

    ok = bool(payload.get("ok"))
    if summary["verified"] > 0:
        lines.append("")
        lines.append("推荐下一步：直接生成图片；auto 会优先使用已验证 provider。")
    elif summary["total"] > 0:
        lines.append("")
        lines.append("推荐下一步：稍后运行 `probe-image-providers --live --candidate-policy all --format human` 重测；如果上游恢复，会自动标记 verified。")
    else:
        lines.append("")
        lines.append("推荐下一步：检查 AiMaMi 当前是否暴露 direct gpt-image-2 provider；不要手动改全局配置。")
    if not ok and payload.get("error"):
        lines.append("")
        lines.append(f"当前阻塞：{(payload.get('error') or {}).get('message')}")
    return "\n".join(lines)


def render_provider_cache_human(payload: dict[str, Any]) -> str:
    outputs = payload.get("outputs") or []
    entries = []
    if outputs and isinstance(outputs[0], dict):
        raw_entries = outputs[0].get("providers")
        entries = raw_entries if isinstance(raw_entries, list) else []
    lines = [
        "Henry Image provider 缓存状态",
        f"- 缓存文件：{(payload.get('metadata') or {}).get('cache_path')}",
        f"- 记录数量：{len(entries)}",
    ]
    if not entries:
        lines.append("- 当前没有缓存记录。")
        lines.append("推荐下一步：运行 `probe-image-providers --format human` 查看当前 AiMaMi provider。")
        return "\n".join(lines)
    lines.append("")
    lines.append("缓存明细：")
    for item in entries:
        cooldown = item.get("cooldown") if isinstance(item.get("cooldown"), dict) else {}
        remaining = cooldown.get("remaining_seconds")
        remaining_text = f"，剩余冷却 {format_duration(remaining)}" if cooldown.get("unusable") else ""
        lines.append(
            f"- {item.get('provider_id')}: "
            f"{item.get('status')}，能力={item.get('image_generation_capability')}，"
            f"{image_provider_cache_reason_zh(item)}{remaining_text}"
        )
    lines.append("")
    lines.append("推荐下一步：如果确认要重新探测已冷却 provider，可运行 `probe-image-providers --reset-cache --format human`，再用 `--live --candidate-policy all` 重测。")
    return "\n".join(lines)


def command_provider_cache(args: argparse.Namespace) -> int:
    action = args.provider_cache_action
    provider = {"type": "henry-image-provider-cache"}
    if action == "status":
        entries = image_provider_cache_entries()
        payload = envelope(
            ok=True,
            command="henry.provider_cache.status",
            status="completed",
            provider=provider,
            outputs=[{"type": "henry_image_provider_cache", "providers": entries}],
            metadata={"cache_path": str(image_provider_health_cache_path()), "count": len(entries)},
        )
        if getattr(args, "format", "json") == "human":
            return emit_human(render_provider_cache_human(payload), ok=True)
        return emit(payload)
    if action == "clear":
        result = clear_image_provider_health_cache(getattr(args, "provider", None))
        payload = envelope(
            ok=True,
            command="henry.provider_cache.clear",
            status="completed",
            provider=provider,
            outputs=[{"type": "henry_image_provider_cache_clear", **result}],
            metadata={"cache_path": str(image_provider_health_cache_path())},
        )
        if getattr(args, "format", "json") == "human":
            if getattr(args, "provider", None):
                removed = "已清理" if result.get("removed") else "没有找到"
                return emit_human(f"Henry Image provider 缓存：{removed} {args.provider}\n缓存文件：{result.get('cache_path')}", ok=True)
            return emit_human(f"Henry Image provider 缓存已清空：{result.get('removed_count', 0)} 条\n缓存文件：{result.get('cache_path')}", ok=True)
        return emit(payload)
    return emit(envelope(
        ok=False,
        command="henry.provider_cache",
        status="validation_error",
        provider=provider,
        error_obj={"message": f"Unsupported provider-cache action: {action}"},
    ))


def image_provider_probe_record(item: dict[str, Any], active_sources: set[str]) -> dict[str, Any]:
    provider_id = str(item.get("provider_id") or "")
    base_url = str(item.get("base_url") or "")
    source = str(item.get("base_url_source") or "")
    cache_entry = image_provider_cache_entry(provider_id)
    temporarily_unusable = image_provider_cache_unusable(cache_entry)
    capability = image_generation_capability_from_cache(cache_entry)
    return {
        "provider_id": provider_id,
        "base_url_source": source,
        "source_kind": item.get("source_kind"),
        "base_url_host": parse.urlparse(base_url).netloc or base_url,
        "responses_endpoint": endpoint(base_url, "/responses"),
        "images_endpoint": endpoint(base_url, "/images/generations"),
        "model": item.get("model"),
        "model_visible": True,
        "responses_endpoint_reachable": "unverified",
        "responses_image_generation_verified": capability == "verified",
        "images_generation_supported": "unverified",
        "image_generation_capability": capability,
        "capability_cache": cache_entry,
        "cooldown": image_provider_cache_cooldown_info(cache_entry),
        "healthScore": item.get("healthScore"),
        "latencyMs": item.get("latencyMs"),
        "lastError": item.get("lastError"),
        "last_error": cache_entry.get("last_error") or item.get("lastError"),
        "recommended_for_auto": source in active_sources and not temporarily_unusable,
        "temporarily_unusable": temporarily_unusable,
        "skip_reason": image_provider_cache_reason(cache_entry) if temporarily_unusable else None,
    }


def http_endpoint_reachable_from_result(result: dict[str, Any]) -> bool | str:
    if result.get("ok"):
        return True
    error_data = result.get("error") or {}
    status = error_data.get("status")
    category = str(error_data.get("category") or classify_api_failure(error_data)).lower()
    if isinstance(status, int):
        return True
    if category in {"network_error", "timeout", "missing_credentials"}:
        return False
    return "unknown"


def update_probe_record_from_result(record: dict[str, Any], route: str, result: dict[str, Any]) -> None:
    status = image_provider_attempt_status(route, result)
    attempt = {
        "route": route,
        "ok": result.get("ok"),
        "status": result.get("status"),
        "error": result.get("error"),
        "request_id": result.get("request_id"),
    }
    record.setdefault("live_attempts", []).append(attempt)
    record["last_error"] = None if result.get("ok") else result.get("error")
    if route == "responses":
        record["responses_endpoint_reachable"] = http_endpoint_reachable_from_result(result)
        record["responses_image_generation_verified"] = bool(result.get("ok"))
    elif route == "images":
        if result.get("ok"):
            record["images_generation_supported"] = True
        elif status == "images_unsupported":
            record["images_generation_supported"] = False
        else:
            record["images_generation_supported"] = "unknown"
    provider_id = record.get("provider_id")
    cache_entry = image_provider_cache_entry(provider_id if isinstance(provider_id, str) else None)
    record["capability_cache"] = cache_entry
    record["image_generation_capability"] = image_generation_capability_from_cache(cache_entry)
    record["temporarily_unusable"] = image_provider_cache_unusable(cache_entry)
    record["recommended_for_auto"] = not record["temporarily_unusable"]


def command_probe_image_providers(args: argparse.Namespace) -> int:
    if getattr(args, "reset_cache", False):
        clear_image_provider_health_cache()
    discovery_route = "responses" if args.route == "images" else args.route
    discovery_args = clone_args(args, base_url=None, route=discovery_route)
    entries = image_model_provider_entries(discovery_args)
    active_args = clone_args(discovery_args, candidate_policy="auto")
    active_candidates = active_image_model_base_url_candidates(active_args)
    active_sources = {source for _, source in active_candidates}
    records = [image_provider_probe_record(item, active_sources) for item in entries]
    image_notes = image_provider_candidate_notes([(str(item["base_url"]), str(item["base_url_source"])) for item in entries])
    metadata: dict[str, Any] = {
        "created_at": now_iso(),
        "live": args.live,
        "image_model": args.image_model,
        "route": args.route,
        "candidate_policy": args.candidate_policy,
        "codex_config_path": str(codex_config_path()),
        "aimami_state_path": str(aimami_state_path()),
        "image_provider_health_cache_path": str(image_provider_health_cache_path()),
        "image_provider_candidates_active": active_candidates,
        **image_notes,
    }
    provider = {"type": "henry-image-provider-probe", "route": args.route}
    if not entries:
        payload = envelope(
            ok=False,
            command="henry.probe_image_providers",
            status="no_image_provider_candidates",
            provider=provider,
            outputs=[{"type": "henry_image_provider_probe", "providers": records}],
            error_obj={"code": "no_image_provider_candidates", "message": "No direct AiMaMi/Codex by-provider image candidates were discovered for the requested image model."},
            metadata=metadata,
        )
        if getattr(args, "format", "json") == "human":
            return emit_human(render_provider_probe_human(payload), ok=False)
        return emit(payload)
    if not args.live:
        metadata["note"] = "probe-image-providers without --live only reads Codex config, AiMaMi state, and Henry Image health cache; it does not spend image quota."
        payload = envelope(
            ok=True,
            command="henry.probe_image_providers",
            status="completed",
            provider=provider,
            outputs=[{"type": "henry_image_provider_probe", "providers": records}],
            metadata=metadata,
        )
        if getattr(args, "format", "json") == "human":
            return emit_human(render_provider_probe_human(payload), ok=True)
        return emit(payload)

    if args.candidate_policy == "strict":
        live_entries = entries[:1]
    elif args.candidate_policy == "all":
        live_entries = entries
    else:
        live_entries = [
            item
            for item in entries
            if str(item.get("base_url_source") or "") in active_sources
        ]
    if not live_entries:
        payload = envelope(
            ok=False,
            command="henry.probe_image_providers",
            status="image_provider_unavailable",
            provider=provider,
            outputs=[{"type": "henry_image_provider_probe", "providers": records}],
            error_obj={"code": "image_provider_unavailable", "message": "All discovered image providers are currently cooling down or marked unusable in the Henry Image health cache."},
            metadata=metadata,
        )
        if getattr(args, "format", "json") == "human":
            return emit_human(render_provider_probe_human(payload), ok=False)
        return emit(payload)

    try:
        prompt = read_prompt(
            args.prompt or "A simple blue ceramic cup on a white table, realistic product photo, natural light, clean background, no text.",
            args.prompt_file,
        )
        validate_common(args)
    except Exception as exc:  # noqa: BLE001
        payload = envelope(
            ok=False,
            command="henry.probe_image_providers",
            status="validation_error",
            provider=provider,
            outputs=[{"type": "henry_image_provider_probe", "providers": records}],
            error_obj={"message": str(exc)},
            metadata=metadata,
        )
        if getattr(args, "format", "json") == "human":
            return emit_human(render_provider_probe_human(payload), ok=False)
        return emit(payload)

    record_by_source = {record["base_url_source"]: record for record in records}
    out_dir = Path(args.out_dir)
    route_plan = ["responses", "images"] if args.route == "auto" else [args.route]
    for item in live_entries:
        base_url = str(item["base_url"])
        base_url_source = str(item["base_url_source"])
        provider_id = str(item.get("provider_id") or "provider")
        safe_provider = re.sub(r"[^A-Za-z0-9_.-]+", "_", provider_id).strip("_") or "provider"
        record = record_by_source.get(base_url_source)
        base_result: dict[str, Any] | None = None
        for route_name in route_plan:
            if route_name == "images" and args.route == "auto" and base_result is not None and not unsupported_responses_result(base_result):
                break
            out_path = out_dir / f"{safe_provider}-{route_name}.png"
            candidate_args = clone_args(
                args,
                base_url=base_url,
                base_url_source=base_url_source,
                route=route_name,
                out=str(out_path),
                force=True,
                dry_run=False,
            )
            payload = build_payload(prompt=prompt, args=candidate_args) if route_name == "responses" else None
            result = run_route_request(
                route=route_name,
                command="henry.probe_image_providers",
                args=candidate_args,
                payload=payload,
                prompt=prompt,
                out=str(out_path),
                extra_metadata={"live_provider_probe": True},
            )
            record_image_provider_attempt(base_url, base_url_source, route_name, result)
            if record is not None:
                update_probe_record_from_result(record, route_name, result)
            if route_name == "responses":
                base_result = result
            if result.get("ok"):
                break
            if route_name == "responses" and args.route == "auto" and unsupported_responses_result(result):
                continue
            break

    ok = any(
        record.get("responses_image_generation_verified") is True or record.get("images_generation_supported") is True
        for record in records
    )
    metadata["image_provider_capability_cache"] = image_provider_health_cache()
    payload = envelope(
        ok=ok,
        command="henry.probe_image_providers",
        status="completed" if ok else "completed_without_verified_provider",
        provider=provider,
        outputs=[{"type": "henry_image_provider_probe", "providers": records}],
        error_obj=None if ok else {"code": "no_verified_image_provider", "message": "Live probe did not verify image generation on any tested provider."},
        metadata=metadata,
    )
    if getattr(args, "format", "json") == "human":
        return emit_human(render_provider_probe_human(payload), ok=ok)
    return emit(payload)


def command_prompt(args: argparse.Namespace) -> int:
    try:
        prompt = read_prompt(args.prompt, args.prompt_file)
        parse_size(args.size)
        if str(args.package_version) not in PROMPT_PACKAGE_VERSIONS:
            raise ValueError("package-version must be 1 or 2.")
        if args.platform not in PROMPT_PLATFORMS:
            raise ValueError("platform must be one of all, openai, flux, sdxl, or midjourney.")
        if args.review_template not in REVIEW_TEMPLATES:
            raise ValueError("review-template must be one of auto, photo, product, social, or engineering.")
    except Exception as exc:  # noqa: BLE001
        return emit_with_workflow(
            envelope(ok=False, command="henry.prompt", status="validation_error", provider={"type": "henry-prompt-only"}, error_obj={"message": str(exc)}),
            args=args,
            command="henry.prompt",
            out="output/imagegen/prompt-package.md",
            persist_on_success=False,
        )
    if str(args.package_version) == "2":
        compiled = compile_prompt_task(
            prompt=prompt,
            explicit_use_case=args.use_case,
            size=args.size,
            negative_prompt=args.negative_prompt,
            review_template=args.review_template,
        )
        package = build_prompt_package_v2(
            original_prompt=prompt,
            compiled_task=compiled,
            size=args.size,
            negative_prompt=args.negative_prompt,
            platform=args.platform,
        )
        metadata: dict[str, Any] = {
            "use_case": compiled["use_case"],
            "package_version": 2,
            "platform": args.platform,
            "review_template": args.review_template,
        }
        if args.explain:
            metadata["compiled_task"] = compiled
            metadata["assumptions"] = compiled["assumptions"]
        return emit_with_workflow(
            envelope(
                ok=True,
                command="henry.prompt",
                status="completed",
                provider={"type": "henry-prompt-only"},
                outputs=[{"type": "henry_prompt_package_v2", "package": package}],
                metadata=metadata,
            ),
            args=args,
            command="henry.prompt",
            out="output/imagegen/prompt-package-v2.json",
        )
    ratio = ratio_from_size(args.size)
    package = {
        "prompt": prompt,
        "negative_prompt": args.negative_prompt,
        "recommended_size": args.size,
        "recommended_ratio": ratio,
        "platforms": {
            "midjourney": {
                "prompt": prompt,
                "parameters": f"--ar {ratio} --style raw --stylize 50 --quality 1",
            },
            "sdxl": {
                "prompt": prompt,
                "negative_prompt": args.negative_prompt,
                "parameters": "CFG 5-7, 25-35 steps, DPM++ 2M Karras",
            },
            "flux": {
                "prompt": prompt,
                "negative_prompt": args.negative_prompt,
                "parameters": "guidance 3.5-5, 20-30 steps",
            },
        },
    }
    return emit_with_workflow(
        envelope(
            ok=True,
            command="henry.prompt",
            status="completed",
            provider={"type": "henry-prompt-only"},
            outputs=[{"type": "henry_prompt_package", "package": package}],
            metadata={"use_case": args.use_case},
        ),
        args=args,
        command="henry.prompt",
        out="output/imagegen/prompt-package.json",
    )


def infer_use_case(prompt: str, explicit_use_case: str | None) -> str:
    value = (explicit_use_case or "").strip()
    if value and value not in {"photorealistic-natural", "auto"}:
        return value
    lowered = prompt.lower()
    if any(token in prompt for token in ("3D 打印", "3d 打印", "CAD", "尺寸", "支架", "图纸", "工程图", "三视图")):
        return "engineering-concept"
    if any(token in prompt for token in ("透明", "抠图", "去背景", "透明背景")):
        return "transparent-cutout"
    if any(token in prompt for token in ("小红书", "封面", "封图", "首图")):
        return "social-cover"
    if any(token in prompt for token in ("产品图", "商品图", "产品渲染")):
        return "product-render"
    if any(token in prompt for token in ("头像", "profile", "avatar")):
        return "avatar"
    if any(token in prompt for token in ("海报", "poster")):
        return "poster"
    if any(token in prompt for token in ("logo", "标志", "品牌标识")):
        return "logo-concept"
    if any(token in prompt for token in ("UI", "界面", "mockup", "线框图")):
        return "UI/mockup"
    if any(token in prompt for token in ("信息图", "infographic", "图解")):
        return "infographic"
    if any(token in prompt for token in ("改图", "修改", "换背景", "修图", "编辑")):
        return "image-edit"
    if "batch" in lowered or "批量" in prompt:
        return "batch-variants"
    return "photo-realistic"


def compile_prompt_task(
    *,
    prompt: str,
    explicit_use_case: str | None,
    size: str,
    negative_prompt: str,
    review_template: str,
) -> dict[str, Any]:
    use_case = infer_use_case(prompt, explicit_use_case)
    assumptions = ["ratio unknown -> using requested/default size " + size]
    traits = casual_traits(prompt)
    subject = prompt
    output_intent = "general high-quality preview image"
    scene = "clean, uncluttered setting"
    style = "realistic, clean, natural light"
    composition = "clear main subject, balanced composition"
    lighting = "soft controlled light"
    color_material = "natural colors and realistic material texture"
    text_requirements = "no generated text unless explicitly requested"
    input_image_roles = "none"
    hard_constraints = ["do not invent brand names, logos, dimensions, or exact text"]
    validation_checklist = ["subject matches request", "style matches requested use case", "no watermark or random logo", "no low-quality artifacts"]

    if "premium" in traits:
        style = "premium, restrained, polished, realistic"
        composition = "uncluttered composition with deliberate negative space"
        lighting = "controlled studio lighting"
        color_material = "premium material feel, realistic surfaces, non-plastic unless requested"
        assumptions.append("高级 -> premium restrained composition and controlled lighting")
    if "realistic" in traits:
        style = "realistic with natural texture and plausible lighting"
        color_material = "non-plastic surfaces, realistic texture"
        assumptions.append("别太假 -> realistic texture and plausible lighting")

    if use_case == "product-render":
        output_intent = "premium product render"
        scene = "clean studio background"
        composition = "centered product, subtle grounded shadow, usable negative space"
        lighting = "soft controlled studio lighting"
        color_material = "accurate product shape and realistic material texture"
        validation_checklist.extend(["product shape is plausible", "no invented logo or text"])
    elif use_case == "social-cover":
        output_intent = "social media cover image"
        scene = "clean editorial/social cover layout"
        composition = "strong focal subject, bright clean composition, usable negative space"
        lighting = "bright but natural light"
        color_material = "fresh, readable, platform-friendly colors"
        validation_checklist.extend(["cover has clear focal hierarchy", "no random embedded text"])
        assumptions.append("小红书/封面 -> social-cover layout with negative space")
    elif use_case == "avatar":
        output_intent = "avatar image"
        scene = "simple clean background"
        composition = "centered face or character, clear silhouette"
        validation_checklist.extend(["avatar reads clearly at small size", "face/character is not distorted"])
    elif use_case == "transparent-cutout":
        output_intent = "transparent or cutout-ready asset"
        scene = "flat removable background or transparent-output route when available"
        composition = "single isolated subject with generous padding"
        hard_constraints.append("keep subject separated from background with crisp edges")
        validation_checklist.extend(["background is removable", "subject edges are clean"])
    elif use_case == "engineering-concept":
        output_intent = "engineering concept or vendor communication asset"
        scene = "clean technical presentation background"
        style = "clear technical concept render or deterministic diagram"
        composition = "front/side/top information should be consistent"
        lighting = "neutral product lighting"
        hard_constraints.append("deterministic output warning: raster output is concept-only; final manufacturing needs SVG/PDF/OpenSCAD/spec")
        validation_checklist.extend(["dimensions are not trusted from pixels", "multi-view geometry is consistent", "switch to deterministic output if structure fails"])
        assumptions.append("engineering keywords -> deterministic output warning included")
    elif use_case == "logo-concept":
        output_intent = "logo concept exploration"
        scene = "plain background"
        style = "simple, vector-friendly mark concept"
        composition = "centered mark with clear silhouette"
        hard_constraints.append("do not copy existing brand marks")
        validation_checklist.extend(["mark is simple", "no copied brand identity"])

    if review_template != "auto":
        assumptions.append("review template forced -> " + review_template)

    canonical_prompt = (
        f"{output_intent}. Subject: {subject}. Scene: {scene}. Style: {style}. "
        f"Composition: {composition}. Lighting: {lighting}. Color/material: {color_material}. "
        f"Text: {text_requirements}. Hard constraints: {'; '.join(hard_constraints)}."
    )
    return {
        "use_case": use_case,
        "output_intent": output_intent,
        "subject": subject,
        "scene": scene,
        "style": style,
        "composition": composition,
        "lighting": lighting,
        "color_material": color_material,
        "text_requirements": text_requirements,
        "input_image_roles": input_image_roles,
        "hard_constraints": hard_constraints,
        "negative_constraints": negative_prompt,
        "execution_route": "built-in image_gen when available; Henry CLI for local output/manifest/probe/batch; prompt package fallback when generation is unavailable",
        "validation_checklist": validation_checklist,
        "assumptions": assumptions,
        "canonical_prompt": canonical_prompt,
    }


def casual_traits(prompt: str) -> set[str]:
    traits: set[str] = set()
    if "高级" in prompt:
        traits.add("premium")
    if "别太假" in prompt or "不要太假" in prompt or "真实" in prompt:
        traits.add("realistic")
    return traits


def build_prompt_package_v2(
    *,
    original_prompt: str,
    compiled_task: dict[str, Any],
    size: str,
    negative_prompt: str,
    platform: str,
) -> dict[str, Any]:
    ratio = ratio_from_size(size)
    canonical = compiled_task["canonical_prompt"]
    platforms: dict[str, Any] = {
        "openai": {
            "prompt": canonical,
            "notes": "Use with built-in image_gen or Responses image_generation.",
        },
        "flux": {
            "prompt": f"{compiled_task['subject']}, {compiled_task['style']}, {compiled_task['composition']}, high quality",
            "negative_prompt": negative_prompt,
            "parameters": "guidance 3.5-5, 20-30 steps",
        },
        "sdxl": {
            "positive": canonical,
            "negative": negative_prompt,
            "parameters": "CFG 5-7, 25-35 steps, DPM++ 2M Karras",
        },
        "midjourney": {
            "prompt": f"{canonical} --ar {ratio} --style raw --stylize 50 --quality 1",
        },
        "comfyui": {
            "positive_prompt": canonical,
            "negative_prompt": negative_prompt,
            "width": parse_size(size)[0] if parse_size(size) else 1024,
            "height": parse_size(size)[1] if parse_size(size) else 1024,
            "seed": "random",
            "note": "Slot map only; ComfyUI is not called in this phase.",
        },
    }
    selected = platforms if platform == "all" else {platform: platforms[platform]}
    return {
        "version": 2,
        "original_prompt": original_prompt,
        "compiled_task": {k: v for k, v in compiled_task.items() if k != "canonical_prompt"},
        "recommended_size": size,
        "recommended_ratio": ratio,
        "platforms": selected,
        "validation_checklist": compiled_task["validation_checklist"],
        "assumptions": compiled_task["assumptions"],
    }


def ratio_from_size(size: str) -> str:
    parsed = parse_size(size)
    if parsed is None:
        return "1:1"
    width, height = parsed
    if width == height:
        return "1:1"
    if width > height and abs((width / height) - 1.5) < 0.05:
        return "3:2"
    if height > width and abs((height / width) - 1.5) < 0.05:
        return "2:3"
    return f"{width}:{height}"


def command_generate(args: argparse.Namespace) -> int:
    if getattr(args, "background_job", False):
        return emit_with_workflow(
            start_background_job("generate", args),
            args=args,
            command="henry.generate",
            out=args.out,
            persist_on_success=False,
        )
    try:
        prompt = read_prompt(args.prompt, args.prompt_file)
        validate_common(args)
        payload = build_payload(prompt=prompt, args=args)
    except Exception as exc:  # noqa: BLE001
        return emit_with_workflow(
            envelope(ok=False, command="henry.generate", status="validation_error", provider=provider_info(normalize_base_url(args.base_url)), error_obj={"message": str(exc)}),
            args=args,
            command="henry.generate",
            out=args.out,
            persist_on_success=False,
        )
    return emit_with_workflow(run_request(command="henry.generate", args=args, payload=payload, prompt=prompt, out=args.out), args=args, command="henry.generate", out=args.out)


def command_edit(args: argparse.Namespace) -> int:
    if getattr(args, "background_job", False):
        return emit_with_workflow(
            start_background_job("edit", args),
            args=args,
            command="henry.edit",
            out=args.out,
            source_output=(args.image or [None])[0],
            persist_on_success=False,
        )
    try:
        prompt = read_prompt(args.prompt, args.prompt_file)
        validate_common(args)
        images = args.image or []
        image_file_ids = args.image_file_id or []
        if not images and not image_file_ids:
            raise ValueError("edit requires at least one --image or --image-file-id.")
        if args.mask and args.mask_file_id:
            raise ValueError("Use --mask or --mask-file-id, not both.")
        payload = build_payload(
            prompt=prompt,
            args=args,
            images=images,
            image_file_ids=image_file_ids,
            mask=args.mask,
            mask_file_id=args.mask_file_id,
        )
    except Exception as exc:  # noqa: BLE001
        return emit_with_workflow(
            envelope(ok=False, command="henry.edit", status="validation_error", provider=provider_info(normalize_base_url(args.base_url)), error_obj={"message": str(exc)}),
            args=args,
            command="henry.edit",
            out=args.out,
            persist_on_success=False,
        )
    source_output = images[0] if images else None
    return emit_with_workflow(
        run_request(
            command="henry.edit",
            args=args,
            payload=payload,
            prompt=prompt,
            out=args.out,
            extra_metadata={"image_count": len(images) + len(image_file_ids), "has_mask": bool(args.mask or args.mask_file_id)},
        ),
        args=args,
        command="henry.edit",
        out=args.out,
        source_output=source_output,
    )


def command_batch(args: argparse.Namespace) -> int:
    if getattr(args, "background_job", False):
        return emit_with_workflow(
            start_background_job("batch", args),
            args=args,
            command="henry.batch",
            out=args.out_dir,
            source_output=args.input,
            persist_on_success=False,
        )
    input_path = Path(args.input)
    if not input_path.exists():
        return emit_with_workflow(
            envelope(ok=False, command="henry.batch", status="validation_error", provider=provider_info(normalize_base_url(args.base_url)), error_obj={"message": f"Batch input not found: {input_path}"}),
            args=args,
            command="henry.batch",
            out=args.out_dir,
            source_output=str(input_path),
            persist_on_success=False,
        )
    if args.concurrency < 1 or args.concurrency > MAX_BATCH_CONCURRENCY:
        return emit_with_workflow(
            envelope(
                ok=False,
                command="henry.batch",
                status="validation_error",
                provider=provider_info(normalize_base_url(args.base_url)),
                error_obj={"code": "bad_concurrency", "message": f"--concurrency must be between 1 and {MAX_BATCH_CONCURRENCY}."},
            ),
            args=args,
            command="henry.batch",
            out=args.out_dir,
            source_output=str(input_path),
            persist_on_success=False,
        )
    if args.max_images is not None and args.max_images < 1:
        return emit_with_workflow(
            envelope(
                ok=False,
                command="henry.batch",
                status="validation_error",
                provider=provider_info(normalize_base_url(args.base_url)),
                error_obj={"code": "bad_max_images", "message": "--max-images must be 1 or greater."},
            ),
            args=args,
            command="henry.batch",
            out=args.out_dir,
            source_output=str(input_path),
            persist_on_success=False,
        )
    tasks: list[dict[str, Any]] = []
    for line_no, line in enumerate(input_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            task = json.loads(line)
        except json.JSONDecodeError as exc:
            return emit_with_workflow(
                envelope(ok=False, command="henry.batch", status="validation_error", provider=provider_info(normalize_base_url(args.base_url)), error_obj={"message": f"Invalid JSONL at line {line_no}: {exc}"}),
                args=args,
                command="henry.batch",
                out=args.out_dir,
                source_output=str(input_path),
                persist_on_success=False,
            )
        task["_line"] = line_no
        tasks.append(task)
    if not tasks:
        return emit_with_workflow(
            envelope(ok=False, command="henry.batch", status="validation_error", provider=provider_info(normalize_base_url(args.base_url)), error_obj={"message": "Batch input contains no tasks."}),
            args=args,
            command="henry.batch",
            out=args.out_dir,
            source_output=str(input_path),
            persist_on_success=False,
        )
    requested_images = sum(int(task.get("n", args.n) or 1) for task in tasks)
    if args.max_images is not None and requested_images > args.max_images:
        payload = envelope(
            ok=bool(args.dry_run),
            command="henry.batch",
            status="dry_run" if args.dry_run else "validation_error",
            provider=provider_info(normalize_base_url(args.base_url)),
            outputs=[{"type": "henry_batch_results", "results": []}],
            error_obj=None if args.dry_run else {"code": "max_images_exceeded", "message": f"Batch requests {requested_images} images, above --max-images {args.max_images}."},
            metadata={"task_count": len(tasks), "requested_images": requested_images, "max_images": args.max_images},
        )
        return emit_with_workflow(payload, args=args, command="henry.batch", out=args.out_dir, source_output=str(input_path), persist_on_success=False)

    result_jsonl_path = Path(args.result_jsonl) if args.result_jsonl else Path(args.out_dir) / "results.jsonl"
    completed_indexes: set[int] = set()
    if args.resume and result_jsonl_path.exists():
        for line in result_jsonl_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            index = row.get("task_index") or (row.get("metadata") or {}).get("batch_index")
            if isinstance(index, int) and row.get("ok") and row.get("status") != "skipped":
                completed_indexes.add(index)

    def task_out(index: int, task: dict[str, Any]) -> str:
        output_format = task.get("output_format", args.output_format)
        return task.get("out") or str(Path(args.out_dir) / f"henry-image-{index}.{output_format}")

    def append_batch_result(index: int, result: dict[str, Any]) -> None:
        result_jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        row = {"task_index": index, **redact(result)}
        with result_jsonl_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def skip_result(index: int, reason: str, out: str) -> dict[str, Any]:
        return envelope(
            ok=True,
            command="henry.batch.skip",
            status="skipped",
            provider=provider_info(normalize_base_url(args.base_url)),
            metadata={"batch_index": index, "reason": reason, "out": out},
        )

    def run_task(index: int, task: dict[str, Any]) -> dict[str, Any]:
        task_args = argparse.Namespace(**vars(args))
        task_args.prompt = task.get("prompt")
        task_args.prompt_file = task.get("prompt_file")
        task_args.size = task.get("size", args.size)
        task_args.quality = task.get("quality", args.quality)
        task_args.model = task.get("model", args.model)
        task_args.image_model = task.get("image_model", args.image_model)
        task_args.base_url = task.get("base_url", args.base_url)
        task_args.route = task.get("route", args.route)
        task_args.candidate_policy = task.get("candidate_policy", args.candidate_policy)
        task_args.n = task.get("n", args.n)
        task_args.images_response_format = task.get("images_response_format", args.images_response_format)
        task_args.images_compat = task.get("images_compat", args.images_compat)
        task_args.input_fidelity = task.get("input_fidelity", args.input_fidelity)
        task_args.output_format = task.get("output_format", args.output_format)
        task_args.output_compression = task.get("output_compression", args.output_compression)
        task_args.background = task.get("background", args.background)
        task_args.moderation = task.get("moderation", args.moderation)
        task_args.partial_images = task.get("partial_images", args.partial_images)
        task_args.timeout = task.get("timeout", args.timeout)
        task_args.retries = task.get("retries", args.retries)
        task_args.api_key_env = task.get("api_key_env", args.api_key_env)
        out_dir = Path(args.out_dir)
        task_args.out = task.get("out") or str(out_dir / f"henry-image-{index}.{task_args.output_format}")
        task_args.image = task.get("image", [])
        if isinstance(task_args.image, str):
            task_args.image = [task_args.image]
        task_args.image_file_id = task.get("image_file_id", [])
        if isinstance(task_args.image_file_id, str):
            task_args.image_file_id = [task_args.image_file_id]
        task_args.mask = task.get("mask")
        task_args.mask_file_id = task.get("mask_file_id")
        try:
            prompt = read_prompt(task_args.prompt, task_args.prompt_file)
            validate_common(task_args)
            if task_args.image or task_args.image_file_id:
                payload = build_payload(
                    prompt=prompt,
                    args=task_args,
                    images=task_args.image,
                    image_file_ids=task_args.image_file_id,
                    mask=task_args.mask,
                    mask_file_id=task_args.mask_file_id,
                )
                return run_request(command="henry.batch.edit", args=task_args, payload=payload, prompt=prompt, out=task_args.out, extra_metadata={"batch_index": index})
            payload = build_payload(prompt=prompt, args=task_args)
            return run_request(command="henry.batch.generate", args=task_args, payload=payload, prompt=prompt, out=task_args.out, extra_metadata={"batch_index": index})
        except Exception as exc:  # noqa: BLE001
            return envelope(ok=False, command="henry.batch.task", status="validation_error", provider=provider_info(normalize_base_url(args.base_url)), error_obj={"message": str(exc)}, metadata={"batch_index": index})

    results: list[dict[str, Any]] = []
    scheduled: list[tuple[int, dict[str, Any]]] = []
    for idx, task in enumerate(tasks, start=1):
        out = task_out(idx, task)
        if args.resume and idx in completed_indexes:
            result = skip_result(idx, "resume", out)
            results.append(result)
            append_batch_result(idx, result)
            continue
        if args.skip_existing and Path(out).exists():
            result = skip_result(idx, "existing_output", out)
            results.append(result)
            append_batch_result(idx, result)
            continue
        scheduled.append((idx, task))
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as executor:
        futures = {executor.submit(run_task, idx, task): idx for idx, task in scheduled}
        for future in as_completed(futures):
            idx = futures[future]
            result = future.result()
            results.append(result)
            append_batch_result(idx, result)
    results.sort(key=lambda item: item.get("metadata", {}).get("batch_index", 0))
    ok = all(item.get("ok") for item in results)
    return emit_with_workflow(
        envelope(
            ok=ok,
            command="henry.batch",
            status="completed" if ok else "completed_with_errors",
            provider=provider_info(normalize_base_url(args.base_url)),
            outputs=[{"type": "henry_batch_results", "results": results}],
            metadata={
                "task_count": len(tasks),
                "scheduled_count": len(scheduled),
                "success_count": sum(1 for item in results if item.get("ok")),
                "result_jsonl": str(result_jsonl_path),
                "requested_images": requested_images,
            },
        ),
        args=args,
        command="henry.batch",
        out=args.out_dir,
        source_output=str(input_path),
    )


def command_quick_validate(args: argparse.Namespace) -> int:
    isolated_env_keys = {
        "HENRY_IMAGE_DISABLE_WINDOWS_USER_ENV",
        *DEDICATED_BASE_URL_ENV_NAMES,
        *DEDICATED_API_KEY_ENV_NAMES,
        *DEFAULT_MODEL_ENV_NAMES,
        *DEFAULT_IMAGE_MODEL_ENV_NAMES,
    }
    old_quick_validate_env = {key: os.environ.get(key) for key in isolated_env_keys}
    os.environ["HENRY_IMAGE_DISABLE_WINDOWS_USER_ENV"] = "1"
    for key in isolated_env_keys:
        if key == "HENRY_IMAGE_DISABLE_WINDOWS_USER_ENV":
            continue
        os.environ.pop(key, None)
    issues: list[str] = []
    required_files = [
        SKILL_ROOT / "SKILL.md",
        SKILL_ROOT / "scripts" / "henry_image.py",
        SKILL_ROOT / "scripts" / "henry_image_core" / "__init__.py",
        SKILL_ROOT / "scripts" / "henry_image_core" / "contracts.py",
        SKILL_ROOT / "scripts" / "henry_image_core" / "cli.py",
        SKILL_ROOT / "scripts" / "henry_image_core" / "workflow.py",
        SKILL_ROOT / "scripts" / "henry_image_core" / "validate.py",
        SKILL_ROOT / "scripts" / "henry_image_core" / "prompts.py",
        SKILL_ROOT / "scripts" / "henry_image_core" / "request.py",
        SKILL_ROOT / "scripts" / "henry_image_core" / "auth.py",
        SKILL_ROOT / "scripts" / "henry_image_core" / "providers.py",
        SKILL_ROOT / "scripts" / "henry_image_core" / "routing.py",
        SKILL_ROOT / "scripts" / "henry_image_core" / "jobs.py",
        SKILL_ROOT / "references" / "api.md",
        SKILL_ROOT / "references" / "routing.md",
        SKILL_ROOT / "references" / "prompts.md",
        SKILL_ROOT / "references" / "roles.md",
        SKILL_ROOT / "references" / "failure.md",
        SKILL_ROOT / "references" / "engineering-diagrams.md",
        SKILL_ROOT / "references" / "prompt-packages.md",
        SKILL_ROOT / "references" / "understanding.md",
        SKILL_ROOT / "references" / "prompt-compiler.md",
        SKILL_ROOT / "references" / "quick-card.md",
        SKILL_ROOT / "references" / "setup.md",
        SKILL_ROOT / "references" / "workflow-map.md",
        SKILL_ROOT / "references" / "runbooks.md",
        SKILL_ROOT / "references" / "review.md",
        SKILL_ROOT / "agents" / "openai.yaml",
    ]
    for path in required_files:
        if not path.exists():
            issues.append(f"Missing required file: {path}")

    skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8") if (SKILL_ROOT / "SKILL.md").exists() else ""
    if "name: henry-image" not in skill_text:
        issues.append("SKILL.md frontmatter must include name: henry-image")
    if "description:" not in skill_text:
        issues.append("SKILL.md frontmatter must include description")
    for expected in (
        "deterministic engineering drawings",
        "Input Image Roles",
        "Failure Policy",
        "prompt-packages.md",
        "Prompt Understanding",
        "Prompt Compiler",
        "Quality Review",
        "must actually call the Henry CLI",
        "gpt-image-2",
        "--candidate-policy auto",
        "OpenAI",
        "Workflow Map",
        "replay_command",
        "next_action",
    ):
        if expected not in skill_text:
            issues.append(f"SKILL.md missing routing guidance: {expected}")

    reference_expectations = {
        "workflow-map.md": ("Workflow Map", "first-use/setup", "generate/edit/batch", "recover/retry"),
        "routing.md": ("Decision tree", "engineering-diagrams.md", "roles.md", "understanding.md", "prompt-compiler.md", "review.md"),
        "roles.md": ("feedback annotation", "dimensional sketch", "previous output"),
        "failure.md": ("API Failures", "Quality Failures", "dimension inconsistency"),
        "engineering-diagrams.md": ("3D printing", "OpenSCAD", "Stop Rule"),
        "prompt-packages.md": ("OpenAI / gpt-image", "Flux", "ComfyUI slot map", "Validation checklist"),
        "understanding.md": ("Image Type Enum", "Default Completion Strategy", "Conflict Handling", "When To Ask Henry"),
        "prompt-compiler.md": ("Canonical Prompt Schema", "Use case:", "Validation checklist"),
        "quick-card.md": ("Route Quick Card", "PowerShell", "--candidate-policy", "--background-job"),
        "runbooks.md": ("character-board", "thumbnail-board", "batch variants", "job-status"),
        "review.md": ("Review Checklist", "Retry Policy", "Stop Conditions"),
    }
    for name, tokens in reference_expectations.items():
        path = SKILL_ROOT / "references" / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for token in tokens:
            if token not in text:
                issues.append(f"{name} missing expected guidance: {token}")

    script_text = Path(__file__).read_text(encoding="utf-8")
    for expected in ("henry.probe", "henry.probe_image_providers", "henry.generate", "henry.edit", "henry.batch", "henry.prompt", "henry.job.start", "henry.job.status", "henry.job.list", "henry.job.cleanup", "henry.job.diagnose", "henry.job.cancel"):
        if expected not in script_text:
            issues.append(f"Missing command contract: {expected}")
    for expected in ("henry-responses-image-generation", "henry-prompt-only", "henry_prompt_package", "henry_batch_results"):
        if expected not in script_text:
            issues.append(f"Missing Henry naming contract: {expected}")
    for expected in ("henry_prompt_package_v2", "--package-version", "--platform", "--explain", "--review-template"):
        if expected not in script_text:
            issues.append(f"Missing prompt compiler contract: {expected}")
    for expected in ("--api-key-env", "--images-response-format", "--images-compat", "--input-fidelity", "/images/edits", "request_multipart", "IMAGES_OPENAI_API_BASE_URL", "IMAGES_OPENAI_API_KEY", "HENRY_IMAGE_API_KEY", "AIMAMI_API_KEY", "AIMAMI_BASE_URL", "api_key_candidates", "api_key_fallback", "BASE_ENDPOINT_SUFFIXES"):
        if expected not in script_text:
            issues.append(f"Missing compatibility contract: {expected}")
    for expected in ("--background-job", "job-status", "DEFAULT_JOBS_DIR", "stream disconnected", "outer timeout", "child_no_result", "--candidate-policy", "--resume", "--result-jsonl", "request_finish", "job-diagnose", "job-cancel", "--diagnose", "--format", "job_cancelled", "cancelled"):
        combined = script_text + "\n" + skill_text + "\n".join(
            (SKILL_ROOT / "references" / name).read_text(encoding="utf-8")
            for name in ("routing.md", "api.md", "failure.md", "quick-card.md", "runbooks.md")
            if (SKILL_ROOT / "references" / name).exists()
        )
        if expected not in combined:
            issues.append(f"Missing long-running job guidance: {expected}")
    for expected in (
        "AuthProfile",
        "auth_plan",
        "auth_shape",
        "header_names",
        "query_names",
        "provider_family",
        "adaptive_reason",
        "api-key",
        "api-version",
        "OpenAI-Organization",
        "OpenAI-Project",
        "DEFAULT_AZURE_API_VERSION",
    ):
        combined = script_text + "\n" + skill_text + "\n".join(
            (SKILL_ROOT / "references" / name).read_text(encoding="utf-8")
            for name in ("routing.md", "api.md", "failure.md", "quick-card.md")
            if (SKILL_ROOT / "references" / name).exists()
        )
        if expected not in combined:
            issues.append(f"Missing adaptive auth guidance: {expected}")

    try:
        if "[REDACTED_SECRET]" not in redact("Authorization: Bearer sk-" + ("a" * 40)):
            issues.append("Behavior self-check failed: redaction")
        if "azure-secret-value" in redact('{"api-key":"azure-secret-value","OpenAI-Project":"proj-secret-value"}'):
            issues.append("Behavior self-check failed: header/query redaction")
        if normalize_base_url("https://example.test/v1/responses") != "https://example.test/v1":
            issues.append("Behavior self-check failed: base URL normalization")
        policy_args = argparse.Namespace(base_url="https://one.example/v1", route="auto", candidate_policy="auto")
        if len(policy_base_url_candidates(policy_args)) != 1:
            issues.append("Behavior self-check failed: candidate policy explicit base-url")
        env_updates = {
            "OPENAI_API_KEY": "sk-quick-validate-openai",
            "AZURE_OPENAI_API_KEY": "quick-validate-azure-key",
            "OPENAI_ORG_ID": "org-quick-validate-secret",
            "OPENAI_PROJECT_ID": "proj-quick-validate-secret",
            "HENRY_LOCAL_RELAY_KEY": "quick-local-relay-key",
        }
        old_env = {key: os.environ.get(key) for key in env_updates}
        try:
            os.environ.update(env_updates)
            openai_profiles = auth_profiles("https://api.openai.com/v1", "default", None, "responses")
            if not openai_profiles or openai_profiles[0].shape != "bearer":
                issues.append("Behavior self-check failed: OpenAI bearer auth profile")
            openai_summary = auth_profile_summary(openai_profiles[0]) if openai_profiles else {}
            if "OpenAI-Organization" not in openai_summary.get("header_names", []) or "OpenAI-Project" not in openai_summary.get("header_names", []):
                issues.append("Behavior self-check failed: OpenAI org/project headers")
            if "org-quick-validate-secret" in json.dumps(redact(openai_profiles[0].headers if openai_profiles else {}), ensure_ascii=False):
                issues.append("Behavior self-check failed: OpenAI org/project redaction")
            azure_profiles = auth_profiles("https://resource.openai.azure.com/openai/deployments/img", "AZURE_OPENAI_ENDPOINT", None, "images")
            if not azure_profiles or azure_profiles[0].shape != "api-key-header":
                issues.append("Behavior self-check failed: Azure api-key auth profile")
            if azure_profiles and ("api-key" not in azure_profiles[0].headers or azure_profiles[0].query.get("api-version") != DEFAULT_AZURE_API_VERSION):
                issues.append("Behavior self-check failed: Azure api-key/api-version injection")
            if azure_profiles and azure_profiles[0].source != "AZURE_OPENAI_API_KEY":
                issues.append("Behavior self-check failed: Azure key priority")
            azure_v1_profiles = auth_profiles("https://resource.openai.azure.com/openai/v1", "AZURE_OPENAI_ENDPOINT", None, "responses")
            if [profile.shape for profile in azure_v1_profiles[:2]] != ["api-key-header", "bearer"]:
                issues.append("Behavior self-check failed: Azure /openai/v1 auth adaptation")
            local_profiles = auth_profiles("http://127.0.0.1:8787/v1", "LOCAL_RELAY_TEST", None, "responses")
            if not local_profiles or local_profiles[0].shape != "no-auth":
                issues.append("Behavior self-check failed: local relay no-auth first")
            if any("Authorization" in profile.headers for profile in local_profiles):
                issues.append("Behavior self-check failed: local relay should not send global OpenAI key")
            explicit_local_profiles = auth_profiles("http://127.0.0.1:8787/v1", "LOCAL_RELAY_TEST", "HENRY_LOCAL_RELAY_KEY", "responses")
            if not any(profile.source == "HENRY_LOCAL_RELAY_KEY" for profile in explicit_local_profiles[1:]):
                issues.append("Behavior self-check failed: local relay explicit key")
            if {"auth_shape", "header_names", "query_names", "provider_family", "adaptive_reason"} - set(auth_profile_summary(azure_profiles[0] if azure_profiles else openai_profiles[0]).keys()):
                issues.append("Behavior self-check failed: adaptive auth summary fields")
            with tempfile.TemporaryDirectory() as tmp_config_dir:
                config_path = Path(tmp_config_dir) / "config.toml"
                config_path.write_text(
                    '\n'.join((
                        'model_provider = "relay"',
                        '[model_providers.relay]',
                        'base_url = "https://relay.example/v1"',
                        'requires_openai_auth = false',
                        '[model_providers.relay.headers]',
                        'Authorization = "Bearer codex-header-secret"',
                        '[model_providers.relay.query]',
                        'tenant = "codex-query-secret"',
                    )),
                    encoding="utf-8",
                )
                old_config = os.environ.get("HENRY_IMAGE_CODEX_CONFIG")
                try:
                    os.environ["HENRY_IMAGE_CODEX_CONFIG"] = str(config_path)
                    config_profiles = auth_profiles("https://relay.example/v1", "codex_config:relay", None, "responses")
                    if not config_profiles or config_profiles[0].source != "codex_config:headers":
                        issues.append("Behavior self-check failed: Codex provider header injection")
                    redacted_config = json.dumps(redact(config_profiles[0].headers if config_profiles else {}), ensure_ascii=False)
                    if "codex-header-secret" in redacted_config:
                        issues.append("Behavior self-check failed: Codex injected header redaction")
                finally:
                    if old_config is None:
                        os.environ.pop("HENRY_IMAGE_CODEX_CONFIG", None)
                    else:
                        os.environ["HENRY_IMAGE_CODEX_CONFIG"] = old_config
            with tempfile.TemporaryDirectory() as tmp_config_dir:
                config_path = Path(tmp_config_dir) / "config.toml"
                state_path = Path(tmp_config_dir) / "state.json"
                cache_path = Path(tmp_config_dir) / "image-provider-health.json"
                config_path.write_text(
                    '\n'.join((
                        'model_provider = "router"',
                        'model = "text_direct"',
                        '',
                        '[model_providers.router]',
                        'base_url = "http://127.0.0.1:25817/codex/router/v1"',
                        'requires_openai_auth = false',
                        '',
                        '[model_providers.image_direct]',
                        'base_url = "http://127.0.0.1:25817/codex/by-provider/image_direct/v1"',
                        'requires_openai_auth = false',
                        '',
                        '[model_providers.text_direct]',
                        'base_url = "http://127.0.0.1:25817/codex/by-provider/text_direct/v1"',
                        'requires_openai_auth = false',
                        '',
                        '[profiles.router]',
                        'model_provider = "router"',
                        'model = "gpt-image-2"',
                        '',
                        '[profiles.image_direct]',
                        'model_provider = "image_direct"',
                        'model = "gpt-image-2"',
                        '',
                        '[profiles.text_direct]',
                        'model_provider = "text_direct"',
                        'model = "gpt-5.5"',
                    )),
                    encoding="utf-8",
                )
                state_path.write_text(json.dumps({
                    "providers": [
                        {"id": "image_direct", "model": "gpt-image-2", "healthScore": 100, "latencyMs": 7, "lastError": None},
                        {"id": "state_image_ok", "model": "gpt-image-2", "healthScore": 90, "latencyMs": 20, "lastError": None},
                        {"id": "state_cold", "model": "gpt-image-2", "healthScore": 95, "latencyMs": 11, "lastError": None},
                        {"id": "state_unsupported", "model": "gpt-image-2", "healthScore": 80, "latencyMs": 15, "lastError": None},
                        {"id": "state_text", "model": "gpt-5.5", "healthScore": 100, "latencyMs": 5, "lastError": None},
                    ],
                    "proxy": {"baseUrl": "http://127.0.0.1:25817"},
                }), encoding="utf-8")
                cache_path.write_text(json.dumps({
                    "version": 1,
                    "providers": {
                        "image_direct": {
                            "provider_id": "image_direct",
                            "status": "verified",
                            "last_success_at": now_iso(),
                        },
                        "state_cold": {
                            "provider_id": "state_cold",
                            "status": "responses_upstream_502",
                            "last_error_at": now_iso(),
                            "last_error": {"status": 502, "message": "upstream 502"},
                        },
                        "state_unsupported": {
                            "provider_id": "state_unsupported",
                            "status": "images_unsupported",
                            "last_error_at": now_iso(),
                            "last_error": {"status": 404, "message": "unsupported_router"},
                        },
                    },
                }), encoding="utf-8")
                old_paths = {
                    "HENRY_IMAGE_CODEX_CONFIG": os.environ.get("HENRY_IMAGE_CODEX_CONFIG"),
                    "HENRY_IMAGE_AIMAMI_STATE": os.environ.get("HENRY_IMAGE_AIMAMI_STATE"),
                    "HENRY_IMAGE_PROVIDER_HEALTH_CACHE": os.environ.get("HENRY_IMAGE_PROVIDER_HEALTH_CACHE"),
                }
                try:
                    os.environ["HENRY_IMAGE_CODEX_CONFIG"] = str(config_path)
                    os.environ["HENRY_IMAGE_AIMAMI_STATE"] = str(state_path)
                    os.environ["HENRY_IMAGE_PROVIDER_HEALTH_CACHE"] = str(cache_path)
                    if codex_provider_model("image_direct") != "gpt-image-2":
                        issues.append("Behavior self-check failed: Codex profile model resolution")
                    response_model, _ = codex_responses_model("codex_config:image_direct")
                    if response_model != "gpt-image-2":
                        issues.append("Behavior self-check failed: Codex image provider response model")
                    state_model, state_model_source = codex_responses_model("aimami_state:state_image_ok")
                    if (state_model, state_model_source) != ("gpt-image-2", "aimami_state"):
                        issues.append("Behavior self-check failed: AiMaMi state provider response model")
                    image_args = argparse.Namespace(
                        base_url=None,
                        route="responses",
                        candidate_policy="auto",
                        model="gpt-image-2",
                        model_source="cli",
                        image_model="gpt-image-2",
                    )
                    image_candidates = image_model_base_url_candidates(image_args)
                    image_sources = [source for _, source in image_candidates]
                    expected_sources = [
                        "codex_config:image_direct",
                        "aimami_state:state_image_ok",
                        "aimami_state:state_cold",
                        "aimami_state:state_unsupported",
                    ]
                    if image_sources != expected_sources:
                        issues.append("Behavior self-check failed: dynamic image model provider discovery/order")
                    if any("/codex/router/" in base_url for base_url, _ in image_candidates):
                        issues.append("Behavior self-check failed: router should be excluded from image candidates")
                    auto_candidates = policy_base_url_candidates(image_args)
                    if [source for _, source in auto_candidates] != expected_sources[:2]:
                        issues.append("Behavior self-check failed: image provider auto health filtering")
                    active_candidates = active_image_model_base_url_candidates(image_args)
                    if active_candidates != auto_candidates:
                        issues.append("Behavior self-check failed: active image provider candidates")
                    image_notes = image_provider_candidate_notes(image_candidates)
                    skipped_sources = [item.get("base_url_source") for item in image_notes.get("skipped_image_provider_candidates", [])]
                    if skipped_sources != expected_sources[2:]:
                        issues.append("Behavior self-check failed: skipped image provider metadata")
                    all_args = clone_args(image_args, candidate_policy="all")
                    all_candidates = policy_base_url_candidates(all_args)
                    if all_candidates[:len(image_candidates)] != image_candidates:
                        issues.append("Behavior self-check failed: image model provider all-policy ordering")
                    strict_args = clone_args(image_args, candidate_policy="strict")
                    if policy_base_url_candidates(strict_args) != image_candidates[:1]:
                        issues.append("Behavior self-check failed: image model provider strict-policy ordering")
                    cli_text_args = clone_args(image_args, model="gpt-5.5", model_source="cli")
                    if image_model_base_url_candidates(cli_text_args):
                        issues.append("Behavior self-check failed: explicit non-image response model should not auto-select image providers")
                finally:
                    for key, value in old_paths.items():
                        if value is None:
                            os.environ.pop(key, None)
                        else:
                            os.environ[key] = value
        finally:
            for key, value in old_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp) / "fake-job"
            job_dir.mkdir()
            stdout_path = job_dir / "stdout.json"
            stderr_path = job_dir / "stderr.jsonl"
            stdout_path.write_text("", encoding="utf-8")
            stderr_path.write_text('{"event":"request_start","route":"responses"}\n', encoding="utf-8")
            write_json_file(job_dir / "job.json", {
                "job_id": "fake-job",
                "status": "running",
                "command": "henry.job.generate",
                "pid": 99999999,
                "stdout": str(stdout_path),
                "stderr": str(stderr_path),
                "created_at": "2026-01-01T00:00:00+00:00",
                "started_at": "2026-01-01T00:00:00+00:00",
            })
            payload = job_status_payload(argparse.Namespace(job=str(job_dir), jobs_dir=None, watch=False, interval=0.01, diagnose=True, tail_lines=80))
            if payload.get("status") != "failed" or (payload.get("error") or {}).get("code") != "child_no_result":
                issues.append("Behavior self-check failed: fake job-status child_no_result")
            diagnosis = (payload.get("outputs") or [{}])[0].get("diagnosis") or {}
            if diagnosis.get("category") != "child_no_result":
                issues.append("Behavior self-check failed: fake job diagnosis")
    except Exception as exc:  # noqa: BLE001
        issues.append(f"Behavior self-check failed: {exc}")

    agent_path = SKILL_ROOT / "agents" / "openai.yaml"
    agent_text = agent_path.read_text(encoding="utf-8") if agent_path.exists() else ""
    for expected in (
        "Generate/edit Henry Image outputs with CLI",
        "call the Henry Image CLI generate/edit path",
        "--candidate-policy auto",
        "gpt-image-2",
        "prompt packages only for explicit prompt-only requests",
    ):
        if expected not in agent_text:
            issues.append(f"agents/openai.yaml missing CLI-first positioning: {expected}")

    if args.strict_names:
        forbidden = (
            "".join(chr(n) for n in (103, 105, 116, 104, 117, 98, 46, 99, 111, 109)),
            "".join(chr(n) for n in (35753, 32771, 26469, 28304)),
            "".join(chr(n) for n in (22806, 37096, 26469, 28304)),
            "".join(chr(n) for n in (115, 111, 117, 114, 99, 101, 32, 116, 114, 97, 99, 101)),
        )
        forbidden_bytes = [token.encode("utf-8") for token in forbidden]
        for path in SKILL_ROOT.rglob("*"):
            if not path.is_file():
                continue
            data = path.read_bytes()
            if any(token in data for token in forbidden_bytes):
                issues.append("Forbidden marker found")
                break

    result = emit(envelope(
        ok=not issues,
        command="henry.quick_validate",
        status="completed" if not issues else "validation_error",
        provider={"type": "henry-local-validator"},
        outputs=[{"type": "henry_validation_results", "issues": issues}],
        error_obj=None if not issues else {"message": "Henry image quick validation failed."},
        metadata={"skill_root": str(SKILL_ROOT), "strict_names": args.strict_names},
    ))
    for key, value in old_quick_validate_env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    return result


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--prompt", default=None)
    parser.add_argument("--prompt-file", default=None)
    parser.add_argument("--size", default=DEFAULT_SIZE)
    parser.add_argument("--quality", default=DEFAULT_QUALITY, choices=sorted(QUALITIES))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--image-model", default=DEFAULT_IMAGE_MODEL, help="Model for Image API routes: /images/generations and /images/edits.")
    parser.add_argument("--base-url", default=None, help="Override OPENAI_BASE_URL for this command.")
    parser.add_argument("--api-key-env", default=None, help="Comma-separated API key environment variable names to check before the built-in/default *_API_KEY search list.")
    parser.add_argument("--route", default="responses", choices=sorted(ROUTES), help="Image route: responses image_generation, Image API, or auto fallback.")
    parser.add_argument("--candidate-policy", default="auto", choices=sorted(CANDIDATE_POLICIES), help="Provider/base-url fallback policy: auto, strict, or all.")
    parser.add_argument("--n", type=int, default=1, help="Number of images requested when the provider supports it.")
    parser.add_argument("--output-format", default=DEFAULT_OUTPUT_FORMAT, choices=sorted(OUTPUT_FORMATS))
    parser.add_argument("--images-response-format", default="auto", choices=sorted(IMAGES_RESPONSE_FORMATS), help="Optional Image API response_format override.")
    parser.add_argument("--images-compat", default="auto", choices=sorted(IMAGES_COMPAT_MODES), help="Image API payload compatibility mode.")
    parser.add_argument("--input-fidelity", default="auto", choices=sorted(INPUT_FIDELITIES), help="Optional Image API edit input_fidelity override.")
    parser.add_argument("--output-compression", type=int, default=None)
    parser.add_argument("--background", default="auto", choices=sorted(BACKGROUNDS))
    parser.add_argument("--moderation", default="auto", choices=sorted(MODERATIONS))
    parser.add_argument("--partial-images", type=int, default=0)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")


def add_background_job_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--background-job", action="store_true", help="Start this generation/edit/batch as a detached local job and return immediately.")
    parser.add_argument("--jobs-dir", default=DEFAULT_JOBS_DIR, help="Directory for background job metadata and stdout/stderr files.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=f"{HENRY_IMAGE_DISPLAY_NAME} generation router helper.")
    parser.add_argument("--version", action="version", version=HENRY_IMAGE_DISPLAY_NAME)
    sub = parser.add_subparsers(dest="command", required=True)

    probe = sub.add_parser("probe", help="Check local image-generation readiness.")
    add_common_args(probe)
    probe.add_argument("--live", action="store_true", help="Run a real minimal image generation capability probe.")
    probe.add_argument("--out", default="output/imagegen/henry-image-probe.png")
    probe.set_defaults(func=command_probe)

    probe_image = sub.add_parser("probe-image-providers", help="Discover and optionally live-test dynamic AiMaMi image providers.")
    add_common_args(probe_image)
    probe_image.add_argument("--live", action="store_true", help="Run a real minimal image generation test for selected providers.")
    probe_image.add_argument("--out-dir", default="output/imagegen/provider-probes")
    probe_image.add_argument("--reset-cache", action="store_true", help="Clear Henry Image provider health cache before discovering/probing providers.")
    probe_image.add_argument("--format", default="json", choices=("json", "human"), help="Output format for provider probe.")
    probe_image.set_defaults(func=command_probe_image_providers)

    provider_cache = sub.add_parser("provider-cache", help="Inspect or clear Henry Image provider health cache.")
    provider_cache_sub = provider_cache.add_subparsers(dest="provider_cache_action", required=True)
    provider_cache_status = provider_cache_sub.add_parser("status", help="Show cached image provider health.")
    provider_cache_status.add_argument("--format", default="json", choices=("json", "human"))
    provider_cache_status.set_defaults(func=command_provider_cache)
    provider_cache_clear = provider_cache_sub.add_parser("clear", help="Clear cached image provider health.")
    provider_cache_clear.add_argument("--provider", default=None, help="Clear one provider id instead of the whole cache.")
    provider_cache_clear.add_argument("--format", default="json", choices=("json", "human"))
    provider_cache_clear.set_defaults(func=command_provider_cache)

    prompt = sub.add_parser("prompt", help="Create a platform-ready prompt package without API calls.")
    prompt.add_argument("--prompt", default=None)
    prompt.add_argument("--prompt-file", default=None)
    prompt.add_argument("--size", default=DEFAULT_SIZE)
    prompt.add_argument("--use-case", default="photorealistic-natural")
    prompt.add_argument("--negative-prompt", default="watermark, text, logo errors, low resolution, distorted hands, deformed objects")
    prompt.add_argument("--package-version", default="1", choices=sorted(PROMPT_PACKAGE_VERSIONS))
    prompt.add_argument("--platform", default="all", choices=sorted(PROMPT_PLATFORMS))
    prompt.add_argument("--explain", action="store_true")
    prompt.add_argument("--review-template", default="auto", choices=sorted(REVIEW_TEMPLATES))
    prompt.set_defaults(func=command_prompt)

    gen = sub.add_parser("generate", help="Generate an image through Responses image_generation or Image API.")
    add_common_args(gen)
    add_background_job_args(gen)
    gen.add_argument("--out", default=DEFAULT_OUT)
    gen.set_defaults(func=command_generate)

    edit = sub.add_parser("edit", help="Edit or use reference images through Responses image_generation or /images/edits.")
    add_common_args(edit)
    add_background_job_args(edit)
    edit.add_argument("--out", default="output/imagegen/henry-image-edit.png")
    edit.add_argument("--image", action="append", default=[])
    edit.add_argument("--image-file-id", action="append", default=[])
    edit.add_argument("--mask", default=None)
    edit.add_argument("--mask-file-id", default=None)
    edit.set_defaults(func=command_edit)

    batch = sub.add_parser("batch", help="Run JSONL image tasks.")
    add_common_args(batch)
    add_background_job_args(batch)
    batch.add_argument("--input", required=True)
    batch.add_argument("--out-dir", default="output/imagegen/batch")
    batch.add_argument("--concurrency", type=int, default=3)
    batch.add_argument("--resume", action="store_true", help="Skip tasks already recorded as successful in --result-jsonl.")
    batch.add_argument("--skip-existing", action="store_true", help="Skip tasks whose output file already exists.")
    batch.add_argument("--result-jsonl", default=None, help="Per-task checkpoint/result JSONL path. Defaults to <out-dir>/results.jsonl.")
    batch.add_argument("--max-images", type=int, default=None, help="Maximum images allowed for a non-dry-run batch.")
    batch.set_defaults(func=command_batch)

    job_status = sub.add_parser("job-status", help="Check a Henry image background job.")
    job_status.add_argument("--job", required=True, help="Job id, job directory, or path to job.json.")
    job_status.add_argument("--jobs-dir", default=DEFAULT_JOBS_DIR)
    job_status.add_argument("--watch", action="store_true", help="Poll until the job reaches a final state.")
    job_status.add_argument("--interval", type=float, default=2.0, help="Polling interval in seconds for --watch.")
    job_status.add_argument("--diagnose", action="store_true", help="Attach a structured diagnosis to the job-status output.")
    job_status.add_argument("--format", default="json", choices=("json", "human"), help="Output format for job status.")
    job_status.add_argument("--tail-lines", type=int, default=80, help="Number of stderr.jsonl tail lines to include in diagnosis.")
    job_status.set_defaults(func=command_job_status)

    job_diagnose = sub.add_parser("job-diagnose", help="Diagnose a Henry image background job.")
    job_diagnose.add_argument("--job", required=True, help="Job id, job directory, or path to job.json.")
    job_diagnose.add_argument("--jobs-dir", default=DEFAULT_JOBS_DIR)
    job_diagnose.add_argument("--format", default="human", choices=("json", "human"))
    job_diagnose.add_argument("--tail-lines", type=int, default=80)
    job_diagnose.set_defaults(func=command_job_diagnose)

    job_cancel = sub.add_parser("job-cancel", help="Conservatively cancel a Henry image background job.")
    job_cancel.add_argument("--job", required=True, help="Job id, job directory, or path to job.json.")
    job_cancel.add_argument("--jobs-dir", default=DEFAULT_JOBS_DIR)
    job_cancel.add_argument("--reason", default=None)
    job_cancel.add_argument("--dry-run", action="store_true")
    job_cancel.add_argument("--format", default="json", choices=("json", "human"))
    job_cancel.set_defaults(func=command_job_cancel)

    job_list = sub.add_parser("job-list", help="List Henry image background jobs.")
    job_list.add_argument("--jobs-dir", default=DEFAULT_JOBS_DIR)
    job_list.set_defaults(func=command_job_list)

    job_cleanup = sub.add_parser("job-cleanup", help="Remove old Henry image background jobs.")
    job_cleanup.add_argument("--jobs-dir", default=DEFAULT_JOBS_DIR)
    job_cleanup.add_argument("--older-than", required=True, help="Remove jobs older than a duration such as 7d, 24h, or 3600s.")
    job_cleanup.set_defaults(func=command_job_cleanup)

    job_runner = sub.add_parser("__job-runner", help=argparse.SUPPRESS)
    job_runner.add_argument("--job-path", required=True)
    job_runner.set_defaults(func=command_job_runner)

    quick = sub.add_parser("quick_validate", help="Run Henry image local skill consistency checks.")
    quick.add_argument("--strict-names", action="store_true")
    quick.set_defaults(func=command_quick_validate)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if hasattr(args, "model") and hasattr(args, "image_model"):
        apply_model_env_defaults(args)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
