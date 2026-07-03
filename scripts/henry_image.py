#!/usr/bin/env python3
"""Henry Image CLI."""

from __future__ import annotations

import argparse
import base64
import contextlib
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
from datetime import datetime, timezone
from typing import Any
from urllib import parse

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from henry_image_core.auth import bearer_headers, env_get, resolve_api_key
from henry_image_core.cli import clone_args
from henry_image_core.contracts import ApiResult
from henry_image_core.jobs import job_id as build_job_id
from henry_image_core.jobs import job_root, parse_duration_seconds, resolve_job_path
from henry_image_core.prompts import build_prompt_package_v2, compile_prompt_task
from henry_image_core.request import (
    classify_api_failure,
    extract_images_api_images,
    extract_response_images,
    failure_error_obj,
    request_json,
    request_multipart,
    write_image_bytes,
    write_manifest,
)
from henry_image_core.validate import read_prompt, validate_common
from henry_image_core.workflow import attach_workflow_metadata


HENRY_IMAGE_VERSION = "0.2.0"
HENRY_IMAGE_DISPLAY_NAME = f"Henry Image V{HENRY_IMAGE_VERSION}"
DEFAULT_SIZE = "1024x1024"
DEFAULT_QUALITY = "medium"
DEFAULT_OUTPUT_FORMAT = "png"
DEFAULT_OUT = "output/imagegen/henry-image.png"
DEFAULT_TIMEOUT = 600
DEFAULT_JOBS_DIR = "output/imagegen/jobs"
DEFAULT_INTERVAL = 5.0

SKILL_ROOT = Path(__file__).resolve().parent.parent
SKILL_CACHE_ROOT = SKILL_ROOT / ".cache"
AGENT_FILE_PATH = SKILL_ROOT / "agents" / "henry-image.yaml"

QUALITIES = {"low", "medium", "high", "auto", "standard", "hd"}
OUTPUT_FORMATS = {"png", "jpeg", "webp"}
IMAGE_RESPONSE_FORMATS = {"auto", "b64_json", "url"}
IMAGE_COMPAT_MODES = {"auto", "minimal"}
INPUT_FIDELITIES = {"auto", "high", "low"}
BACKGROUNDS = {"auto", "opaque", "transparent"}
MODERATIONS = {"auto", "low"}
ROUTES = {"auto", "responses", "images"}
PROMPT_PACKAGE_VERSIONS = {"generic"}
PROMPT_PLATFORMS = {"generic"}
REVIEW_TEMPLATES = {"auto", "photo", "product", "social", "technical"}
BASE_ENDPOINT_SUFFIXES = (
    "/chat/completions",
    "/responses",
    "/images/generations",
    "/images/edits",
)
NO_FALLBACK_CATEGORIES = {
    "invalid_credentials",
    "missing_credentials",
    "content_policy",
    "quota_exceeded",
    "rate_limited",
    "validation_error",
    "bad_parameter",
    "missing_configuration",
}
RETRYABLE_FALLBACK_CATEGORIES = {
    "api_error",
    "network_error",
    "server_error",
    "not_found",
    "timeout",
    "no_image_result",
    "service_unavailable",
}
SECRET_PATTERNS = [
    re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]+", re.IGNORECASE),
    re.compile(r"(?<![A-Za-z0-9])sk-[^\s\"'<>]+"),
]
TEXT_SUFFIXES = {".md", ".py", ".yaml", ".yml", ".json", ".txt"}
def removed_marker(*parts: str) -> str:
    return "".join(parts)


REMOVED_TEXT_MARKERS = (
    removed_marker("Open", "AI"),
    removed_marker("Ai", "MaMi"),
    removed_marker("Cod", "ex"),
    removed_marker("Azu", "re"),
    removed_marker("AO", "AI"),
    removed_marker("Open ", "WebUI"),
    removed_marker("Fl", "ux"),
    removed_marker("Mid", "journey"),
    removed_marker("SD", "XL"),
    removed_marker("Open", "SCAD"),
    removed_marker("gpt", "-image-2"),
    removed_marker("gpt", "-5"),
    removed_marker("probe-image-", "providers"),
    removed_marker("provider-", "cache"),
    removed_marker("candidate-", "policy"),
    removed_marker("agents/", "open", "ai.yaml"),
    removed_marker("HENRY_IMAGE_", "OPEN", "AI_API_KEY"),
    removed_marker("HENRY_IMAGE_", "ACCESS", "_KEY"),
    removed_marker("HENRY_IMAGE_", "API_", "BASE"),
    removed_marker("HENRY_IMAGE_", "API_", "BASE_URL"),
    removed_marker("HENRY_IMAGE_", "RESPONSE", "_MODEL"),
    removed_marker("HENRY_IMAGE_", "MODEL", "_IMAGE"),
    removed_marker("OPEN", "AI_"),
    removed_marker("AZ", "URE_"),
    removed_marker("AO", "AI_"),
    removed_marker("AIM", "AMI_"),
    removed_marker("CODE", "X_"),
    removed_marker("OPEN", "AI_COMP", "AT_"),
    removed_marker("GPT_", "IMAGE_"),
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_base_url(value: str) -> str:
    text = value.strip()
    if not text:
        return text
    parsed = parse.urlparse(text)
    path = parsed.path.rstrip("/")
    lowered = path.lower()
    for suffix in BASE_ENDPOINT_SUFFIXES:
        if lowered.endswith(suffix):
            path = path[: -len(suffix)]
            break
    rebuilt = parsed._replace(path=path or "/v1", params="", query="", fragment="")
    result = parse.urlunparse(rebuilt).rstrip("/")
    return result


def is_data_image_url(value: str) -> bool:
    return value.startswith("data:image/") and ";base64," in value


def sensitive_dict_key(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    normalized = key.strip().lower().replace("-", "_").replace(" ", "_")
    return normalized in {"authorization", "api_key", "x_api_key", "api-key", "token", "secret"}


def redact(value: Any) -> Any:
    if isinstance(value, str):
        text = value
        for pattern in SECRET_PATTERNS:
            text = pattern.sub("[REDACTED_SECRET]", text)
        return text
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return [redact(item) for item in value]
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if sensitive_dict_key(key):
                cleaned[str(key)] = "[REDACTED_SECRET]"
            else:
                cleaned[str(key)] = redact(item)
        return cleaned
    return value


def stderr_event(event: str, **fields: Any) -> None:
    text = json.dumps(redact({"event": event, **fields}), ensure_ascii=False)
    try:
        print(text, file=sys.stderr)
    except UnicodeEncodeError:
        sys.stderr.buffer.write((text + "\n").encode("utf-8", errors="replace"))


def emit(payload: dict[str, Any]) -> int:
    print(json.dumps(redact(payload), ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 1


def emit_human(text: str, *, ok: bool) -> int:
    print(text)
    return 0 if ok else 1


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
        "provider": provider,
        "request_id": request_id,
        "outputs": outputs or [],
        "error": failure_error_obj(error_obj) if error_obj else None,
        "metadata": metadata or {},
    }


def provider_info(base_url: str | None, *, route: str | None = None, base_url_source: str | None = None) -> dict[str, Any]:
    host = parse.urlparse(base_url or "").netloc or base_url or ""
    info = {"type": "henry-remote-service"}
    if host:
        info["base_url_host"] = host
    if route:
        info["route"] = route
    if base_url_source:
        info["base_url_source"] = base_url_source
    return info


def apply_model_env_defaults(args: argparse.Namespace) -> None:
    if getattr(args, "model", None) is None:
        args.model = env_get("HENRY_IMAGE_MODEL")
    if getattr(args, "image_model", None) is None:
        args.image_model = env_get("HENRY_IMAGE_IMAGE_MODEL")


def resolve_base_url(base_url: str | None) -> tuple[str | None, str | None]:
    if base_url:
        return normalize_base_url(base_url), "cli"
    env_value = env_get("HENRY_IMAGE_BASE_URL")
    if env_value:
        return normalize_base_url(env_value), "HENRY_IMAGE_BASE_URL"
    return None, None


def validate_route_requirements(args: argparse.Namespace) -> None:
    if args.route == "responses" and not args.model:
        raise ValueError("model is required for route responses.")
    if args.route == "images" and not args.image_model:
        raise ValueError("image-model is required for route images.")
    if args.route == "auto" and (not args.model or not args.image_model):
        raise ValueError("Both model and image-model are required for route auto.")


def resolve_remote_config(args: argparse.Namespace) -> dict[str, str]:
    apply_model_env_defaults(args)
    base_url, base_url_source = resolve_base_url(getattr(args, "base_url", None))
    if not base_url:
        raise ValueError("base-url is required. Use --base-url or set HENRY_IMAGE_BASE_URL.")
    api_key, auth_source = resolve_api_key(getattr(args, "api_key_env", None))
    if not api_key:
        raise ValueError("api key is required. Set HENRY_IMAGE_API_KEY or use --api-key-env.")
    validate_route_requirements(args)
    return {
        "base_url": base_url,
        "base_url_source": base_url_source or "cli",
        "api_key": api_key,
        "auth_source": auth_source or "HENRY_IMAGE_API_KEY",
    }


def route_metadata(config: dict[str, str], route: str) -> dict[str, Any]:
    return {
        "route": route,
        "auth_source": config["auth_source"],
        "auth_shape": "bearer",
        "base_url_source": config["base_url_source"],
    }


def read_binary_source(value: str, timeout: int) -> tuple[bytes, str]:
    if is_data_image_url(value):
        ext = value.split(";", 1)[0].split("/")[-1]
        return value.encode("utf-8"), f"inline.{ext}"
    if value.startswith("http://") or value.startswith("https://"):
        from henry_image_core.request import download_image

        raw = download_image(value, timeout, is_data_image_url=is_data_image_url)
        filename = Path(parse.urlparse(value).path).name or "remote-image.bin"
        return raw, filename
    path = Path(value)
    return path.read_bytes(), path.name


def to_data_image_url(raw: bytes, filename: str) -> str:
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def decode_data_image_url(value: str) -> tuple[bytes, str]:
    header, encoded = value.split(";base64,", 1)
    ext = header.split("/")[-1] or "bin"
    return base64.b64decode(encoded), f"inline.{ext}"


def build_responses_payload(prompt: str, args: argparse.Namespace, *, edit_inputs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inputs: list[dict[str, Any]] = [{"type": "input_text", "text": prompt}]
    if edit_inputs:
        inputs.extend(edit_inputs)
    return {
        "model": args.model,
        "input": [{"role": "user", "content": inputs}],
        "tools": [
            {
                "type": "image_generation",
                "size": args.size,
                "quality": args.quality,
                "output_format": args.output_format,
            }
        ],
        "tool_choice": {"type": "image_generation"},
    }


def build_images_payload(prompt: str, args: argparse.Namespace) -> dict[str, Any]:
    payload = {
        "model": args.image_model,
        "prompt": prompt,
        "n": args.n,
        "size": args.size,
    }
    if args.images_response_format != "auto":
        payload["response_format"] = args.images_response_format
    if args.output_format:
        payload["output_format"] = args.output_format
    if args.output_compression is not None:
        payload["output_compression"] = args.output_compression
    return payload


def build_edit_inputs(args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[tuple[str, str, bytes]]]:
    response_inputs: list[dict[str, Any]] = []
    multipart_files: list[tuple[str, str, bytes]] = []
    for value in args.image or []:
        if is_data_image_url(value):
            raw, filename = decode_data_image_url(value)
            response_inputs.append({"type": "input_image", "image": value})
            multipart_files.append(("image", filename, raw))
            continue
        raw, filename = read_binary_source(value, args.timeout)
        if value.startswith("http://") or value.startswith("https://"):
            response_inputs.append({"type": "input_image", "image": value})
        else:
            response_inputs.append({"type": "input_image", "image": to_data_image_url(raw, filename)})
        multipart_files.append(("image", filename, raw))
    if args.mask:
        if is_data_image_url(args.mask):
            raw, filename = decode_data_image_url(args.mask)
            response_inputs.append({"type": "input_image", "image": args.mask, "role": "mask"})
        else:
            raw, filename = read_binary_source(args.mask, args.timeout)
            response_inputs.append({"type": "input_image", "image": to_data_image_url(raw, filename), "role": "mask"})
        multipart_files.append(("mask", filename, raw))
    for item in args.image_file_id or []:
        response_inputs.append({"type": "input_image", "image_file_id": item})
    if args.mask_file_id:
        response_inputs.append({"type": "input_image", "mask_file_id": args.mask_file_id})
    return response_inputs, multipart_files


def should_try_images_fallback(result: dict[str, Any]) -> bool:
    if result.get("ok"):
        return False
    status = str(result.get("status") or "")
    if status in NO_FALLBACK_CATEGORIES:
        return False
    error_category = str((result.get("error") or {}).get("category") or "")
    if error_category in NO_FALLBACK_CATEGORIES:
        return False
    return status in RETRYABLE_FALLBACK_CATEGORIES or error_category in RETRYABLE_FALLBACK_CATEGORIES


def create_manifest(
    *,
    command: str,
    route: str,
    args: argparse.Namespace,
    config: dict[str, str],
    provider: dict[str, Any],
    outputs: list[dict[str, Any]],
    request_id: str | None,
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "command": command,
        "route": route,
        "request_id": request_id,
        "provider": provider,
        "config": {
            "base_url_source": config["base_url_source"],
            "auth_source": config["auth_source"],
            "model": args.model,
            "image_model": args.image_model,
            "size": args.size,
            "quality": args.quality,
            "output_format": args.output_format,
        },
        "outputs": outputs,
        "metadata": extra_metadata or {},
    }


def attach_manifest_paths(outputs: list[dict[str, Any]], manifest_path: str) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for item in outputs:
        copy = dict(item)
        copy["manifest"] = manifest_path
        enriched.append(copy)
    return enriched


def attempt_route(
    *,
    route: str,
    command: str,
    args: argparse.Namespace,
    prompt: str,
    out: str,
    config: dict[str, str],
    edit_inputs: list[dict[str, Any]] | None = None,
    multipart_files: list[tuple[str, str, bytes]] | None = None,
) -> dict[str, Any]:
    provider = provider_info(config["base_url"], route=route, base_url_source=config["base_url_source"])
    metadata = route_metadata(config, route)
    headers = bearer_headers(config["api_key"])
    endpoint: str
    stderr_event(
        "request_start",
        command=command,
        route=route,
        endpoint=config["base_url"],
        base_url_source=config["base_url_source"],
        auth_source=config["auth_source"],
        auth_shape="bearer",
    )
    if route == "responses":
        endpoint = config["base_url"] + "/responses"
        payload = build_responses_payload(prompt, args, edit_inputs=edit_inputs)
        result = request_json(endpoint, headers, payload, args.timeout, ApiResult)
        stderr_event(
            "request_finish",
            command=command,
            route=route,
            endpoint=endpoint,
            base_url_source=config["base_url_source"],
            auth_source=config["auth_source"],
            auth_shape="bearer",
            ok=result.ok,
            status=result.status,
            error_code=(result.error or {}).get("code"),
            request_id=result.request_id,
        )
        if not result.ok:
            error_obj = failure_error_obj(result.error)
            return envelope(
                ok=False,
                command=command,
                status=error_obj["category"],
                provider=provider,
                error_obj=error_obj,
                metadata=metadata,
                request_id=result.request_id,
            )
        images_b64 = extract_response_images(result.data or {})
        if not images_b64:
            return envelope(
                ok=False,
                command=command,
                status="no_image_result",
                provider=provider,
                error_obj={"code": "no_image_result", "message": "Remote service returned no image bytes."},
                metadata=metadata,
                request_id=result.request_id,
            )
        outputs = write_image_bytes(
            [__import__("base64").b64decode(item) for item in images_b64],
            out,
            args.output_format,
            args.force,
        )
    else:
        endpoint = config["base_url"] + ("/images/edits" if edit_inputs else "/images/generations")
        if edit_inputs:
            fields = {"model": args.image_model, "prompt": prompt, "size": args.size, "n": str(args.n)}
            result = request_multipart(endpoint, headers, fields, multipart_files or [], args.timeout, ApiResult)
        else:
            payload = build_images_payload(prompt, args)
            result = request_json(endpoint, headers, payload, args.timeout, ApiResult)
        stderr_event(
            "request_finish",
            command=command,
            route=route,
            endpoint=endpoint,
            base_url_source=config["base_url_source"],
            auth_source=config["auth_source"],
            auth_shape="bearer",
            ok=result.ok,
            status=result.status,
            error_code=(result.error or {}).get("code"),
            request_id=result.request_id,
        )
        if not result.ok:
            error_obj = failure_error_obj(result.error)
            return envelope(
                ok=False,
                command=command,
                status=error_obj["category"],
                provider=provider,
                error_obj=error_obj,
                metadata=metadata,
                request_id=result.request_id,
            )
        images_raw = extract_images_api_images(result.data or {}, timeout=args.timeout, is_data_image_url=is_data_image_url)
        if not images_raw:
            return envelope(
                ok=False,
                command=command,
                status="no_image_result",
                provider=provider,
                error_obj={"code": "no_image_result", "message": "Remote service returned no image bytes."},
                metadata=metadata,
                request_id=result.request_id,
            )
        outputs = write_image_bytes(images_raw, out, args.output_format, args.force)

    manifest = create_manifest(
        command=command,
        route=route,
        args=args,
        config=config,
        provider=provider,
        outputs=outputs,
        request_id=result.request_id,
        extra_metadata=metadata,
    )
    manifest_path = write_manifest(out, manifest, args.force, redact=redact)
    enriched = attach_manifest_paths(outputs, manifest_path)
    metadata["request_id"] = result.request_id
    return envelope(
        ok=True,
        command=command,
        status="completed",
        provider=provider,
        outputs=enriched,
        metadata=metadata,
        request_id=result.request_id,
    )


def run_image_command_result(
    *,
    command: str,
    args: argparse.Namespace,
    out: str,
    source_output: str | None = None,
    persist_on_success: bool = True,
) -> dict[str, Any]:
    validate_common(
        args,
        qualities=QUALITIES,
        output_formats=OUTPUT_FORMATS,
        image_response_formats=IMAGE_RESPONSE_FORMATS,
        image_compat_modes=IMAGE_COMPAT_MODES,
        input_fidelities=INPUT_FIDELITIES,
        backgrounds=BACKGROUNDS,
        moderations=MODERATIONS,
        routes=ROUTES,
    )
    prompt = read_prompt(args.prompt, args.prompt_file)
    edit_inputs: list[dict[str, Any]] | None = None
    multipart_files: list[tuple[str, str, bytes]] | None = None
    is_edit = command.endswith(".edit")
    if is_edit:
        edit_inputs, multipart_files = build_edit_inputs(args)
        if not edit_inputs:
            return envelope(
                ok=False,
                command=command,
                status="validation_error",
                provider={"type": "henry-local-validator"},
                error_obj={"message": "Edit requires at least one image input."},
            )

    try:
        config = resolve_remote_config(args)
    except ValueError as exc:
        return envelope(
            ok=False,
            command=command,
            status="validation_error",
            provider={"type": "henry-local-validator"},
            error_obj={"message": str(exc)},
        )

    metadata = route_metadata(config, args.route)
    provider = provider_info(config["base_url"], route=args.route, base_url_source=config["base_url_source"])
    if args.dry_run:
        payload = envelope(
            ok=True,
            command=command,
            status="dry_run",
            provider=provider,
            outputs=[{"type": "henry_dry_run", "prompt": prompt, "route": args.route}],
            metadata=metadata,
        )
        return attach_workflow_metadata(
            payload,
            cache_root=SKILL_CACHE_ROOT,
            args=args,
            command=command,
            out=out,
            source_output=source_output,
            persist_on_success=False,
        )

    attempted_routes: list[str] = []
    routes = ["responses", "images"] if args.route == "auto" else [args.route]
    final_result: dict[str, Any] | None = None
    for route in routes:
        attempted_routes.append(route)
        final_result = attempt_route(
            route=route,
            command=command,
            args=args,
            prompt=prompt,
            out=out,
            config=config,
            edit_inputs=edit_inputs if route == "responses" or is_edit else None,
            multipart_files=multipart_files,
        )
        if final_result.get("ok"):
            break
        if route == "responses" and args.route == "auto" and should_try_images_fallback(final_result):
            continue
        break

    assert final_result is not None
    final_result.setdefault("metadata", {})["route_attempted"] = attempted_routes
    if final_result.get("ok"):
        final_result["provider"]["route"] = attempted_routes[-1]
    return attach_workflow_metadata(
        final_result,
        cache_root=SKILL_CACHE_ROOT,
        args=args,
        command=command,
        out=out,
        source_output=source_output,
        persist_on_success=persist_on_success,
    )


def build_batch_task_args(args: argparse.Namespace, task: dict[str, Any], index: int) -> argparse.Namespace:
    output_format = task.get("output_format") or args.output_format
    out_value = task.get("out") or str(Path(args.out_dir) / f"henry-image-{index}.{output_format}")
    return clone_args(
        args,
        prompt=task.get("prompt"),
        prompt_file=task.get("prompt_file"),
        image=task.get("image") or [],
        image_file_id=task.get("image_file_id") or [],
        mask=task.get("mask"),
        mask_file_id=task.get("mask_file_id"),
        route=task.get("route", args.route),
        base_url=task.get("base_url", args.base_url),
        api_key_env=task.get("api_key_env", args.api_key_env),
        model=task.get("model", args.model),
        image_model=task.get("image_model", args.image_model),
        size=task.get("size", args.size),
        quality=task.get("quality", args.quality),
        output_format=output_format,
        out=out_value,
        background_job=False,
        dry_run=False,
    )


def build_child_argv(command_name: str, args: argparse.Namespace) -> list[str]:
    argv = [command_name]

    def add(flag: str, value: Any) -> None:
        if value is None or value is False:
            return
        if value is True:
            argv.append(flag)
            return
        if isinstance(value, list):
            for item in value:
                argv.extend([flag, str(item)])
            return
        argv.extend([flag, str(value)])

    add("--prompt", getattr(args, "prompt", None))
    add("--prompt-file", getattr(args, "prompt_file", None))
    add("--image", getattr(args, "image", None))
    add("--image-file-id", getattr(args, "image_file_id", None))
    add("--mask", getattr(args, "mask", None))
    add("--mask-file-id", getattr(args, "mask_file_id", None))
    add("--size", getattr(args, "size", None))
    add("--quality", getattr(args, "quality", None))
    add("--model", getattr(args, "model", None))
    add("--image-model", getattr(args, "image_model", None))
    add("--base-url", getattr(args, "base_url", None))
    add("--api-key-env", getattr(args, "api_key_env", None))
    add("--route", getattr(args, "route", None))
    add("--output-format", getattr(args, "output_format", None))
    add("--images-response-format", getattr(args, "images_response_format", None))
    add("--images-compat", getattr(args, "images_compat", None))
    add("--input-fidelity", getattr(args, "input_fidelity", None))
    add("--background", getattr(args, "background", None))
    add("--moderation", getattr(args, "moderation", None))
    add("--partial-images", getattr(args, "partial_images", None))
    add("--timeout", getattr(args, "timeout", None))
    add("--retries", getattr(args, "retries", None))
    add("--output-compression", getattr(args, "output_compression", None))
    add("--negative-prompt", getattr(args, "negative_prompt", None))
    add("--use-case", getattr(args, "use_case", None))
    add("--review-template", getattr(args, "review_template", None))
    add("--platform", getattr(args, "platform", None))
    add("--package-version", getattr(args, "package_version", None))
    if getattr(args, "explain", False):
        argv.append("--explain")
    if getattr(args, "force", False):
        argv.append("--force")
    if getattr(args, "n", None) is not None:
        add("--n", args.n)
    if command_name == "batch":
        add("--batch-input", getattr(args, "batch_input", None))
        add("--out-dir", getattr(args, "out_dir", None))
    else:
        add("--out", getattr(args, "out", None))
    return argv


def write_job_metadata(job_dir: Path, metadata: dict[str, Any]) -> None:
    (job_dir / "job.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


def read_job_metadata(job_dir: Path) -> dict[str, Any]:
    return json.loads((job_dir / "job.json").read_text(encoding="utf-8"))


def pid_running(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def start_background_job(command_name: str, args: argparse.Namespace) -> int:
    jobs_path = job_root(getattr(args, "jobs_dir", None) or DEFAULT_JOBS_DIR, DEFAULT_JOBS_DIR)
    jobs_path.mkdir(parents=True, exist_ok=True)
    current_job_id = build_job_id()
    job_dir = jobs_path / current_job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = job_dir / "stdout.json"
    stderr_path = job_dir / "stderr.jsonl"
    argv = build_child_argv(command_name, clone_args(args, background_job=False))
    with open(stdout_path, "w", encoding="utf-8") as stdout_handle, open(stderr_path, "w", encoding="utf-8") as stderr_handle:
        process = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), *argv],
            cwd=os.getcwd(),
            env=os.environ.copy(),
            stdout=stdout_handle,
            stderr=stderr_handle,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    metadata = {
        "job_id": current_job_id,
        "status": "running",
        "command": f"henry.{command_name}",
        "pid": process.pid,
        "created_at": now_iso(),
        "started_at": now_iso(),
        "job_path": str(job_dir),
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
        "out": getattr(args, "out", getattr(args, "out_dir", None)),
        "argv": argv,
    }
    write_job_metadata(job_dir, metadata)
    payload = envelope(
        ok=True,
        command="henry.job.start",
        status="started",
        provider={"type": "henry-background-job"},
        outputs=[
            {
                "type": "henry_job",
                "job_id": current_job_id,
                "job_dir": str(job_dir),
                "pid": process.pid,
                "stdout": str(stdout_path),
                "stderr": str(stderr_path),
            }
        ],
        metadata={"route": args.route},
    )
    return emit(payload)


def load_child_result(job_dir: Path) -> tuple[dict[str, Any] | None, str]:
    stdout_path = job_dir / "stdout.json"
    if not stdout_path.exists():
        return None, "child_no_result"
    text = stdout_path.read_text(encoding="utf-8").strip()
    if not text:
        return None, "child_no_result"
    try:
        return json.loads(text), "completed"
    except json.JSONDecodeError:
        return None, "child_invalid_json"


def infer_job_state(job_dir: Path, metadata: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    result, fallback = load_child_result(job_dir)
    if result is not None:
        if metadata.get("status") != "cancelled":
            metadata["status"] = result.get("status") or "completed"
            write_job_metadata(job_dir, metadata)
        return str(metadata.get("status") or "completed"), result
    if pid_running(int(metadata.get("pid") or 0)):
        return "running", None
    return fallback, None


def build_job_diagnosis(job_dir: Path, metadata: dict[str, Any], result: dict[str, Any] | None, state: str) -> dict[str, Any]:
    category = state
    message = "Job is still running."
    if result:
        category = str(result.get("status") or state)
        error_obj = result.get("error") or {}
        message = str(error_obj.get("message") or category)
    elif state == "child_invalid_json":
        message = "The background job completed without a valid JSON result."
    elif state == "child_no_result":
        message = "The background job completed without writing a result payload."
    next_action = {
        "running": "Keep polling with job-status --watch, or cancel the job if it is no longer needed.",
        "rate_limited": "Wait for the service to recover, then rerun the same command.",
        "child_invalid_json": "Inspect stderr.jsonl, then rerun after fixing the child command output.",
        "child_no_result": "Inspect stderr.jsonl, then rerun after fixing the child command output.",
        "cancelled": "Review the job directory and rerun only if the work is still needed.",
    }.get(category, "Inspect the job directory and rerun after fixing the reported blocker.")
    return {
        "category": category,
        "message": message,
        "next_action": next_action,
        "evidence": [str(job_dir), str(metadata.get("stdout")), str(metadata.get("stderr"))],
    }


def command_job_status(args: argparse.Namespace) -> int:
    job_dir = resolve_job_path(args.job, args.jobs_dir, DEFAULT_JOBS_DIR)
    if not job_dir.exists():
        return emit(
            envelope(
                ok=False,
                command="henry.job.status",
                status="not_found",
                provider={"type": "henry-background-job"},
                error_obj={"message": f"Job not found: {job_dir}"},
            )
        )
    while True:
        metadata = read_job_metadata(job_dir)
        state, result = infer_job_state(job_dir, metadata)
        if not args.watch or state != "running":
            break
        time.sleep(max(args.interval, 0.1))
    payload = {
        "type": "henry_job_status",
        "job_id": metadata.get("job_id"),
        "job_dir": str(job_dir),
        "status": state,
    }
    if result is not None:
        payload["result"] = redact(result)
    if args.diagnose:
        payload["diagnosis"] = build_job_diagnosis(job_dir, metadata, result, state)
    return emit(
        envelope(
            ok=state not in {"not_found"},
            command="henry.job.status",
            status=state,
            provider={"type": "henry-background-job"},
            outputs=[payload],
        )
    )


def command_job_diagnose(args: argparse.Namespace) -> int:
    job_dir = resolve_job_path(args.job, args.jobs_dir, DEFAULT_JOBS_DIR)
    if not job_dir.exists():
        return emit(
            envelope(
                ok=False,
                command="henry.job.diagnose",
                status="not_found",
                provider={"type": "henry-background-job"},
                error_obj={"message": f"Job not found: {job_dir}"},
            )
        )
    metadata = read_job_metadata(job_dir)
    state, result = infer_job_state(job_dir, metadata)
    diagnosis = build_job_diagnosis(job_dir, metadata, result, state)
    if args.format == "human":
        lines = [
            f"Blocker: {diagnosis['category']}",
            f"Summary: {diagnosis['message']}",
            "Evidence:",
        ]
        for item in diagnosis["evidence"]:
            lines.append(f"- {item}")
        lines.append(f"Next action: {diagnosis['next_action']}")
        return emit_human("\n".join(lines), ok=True)
    return emit(
        envelope(
            ok=True,
            command="henry.job.diagnose",
            status=state,
            provider={"type": "henry-background-job"},
            outputs=[
                {
                    "type": "henry_job_diagnosis",
                    "job_id": metadata.get("job_id"),
                    "job_dir": str(job_dir),
                    "diagnosis": diagnosis,
                }
            ],
        )
    )


def command_job_cancel(args: argparse.Namespace) -> int:
    job_dir = resolve_job_path(args.job, args.jobs_dir, DEFAULT_JOBS_DIR)
    if not job_dir.exists():
        return emit(
            envelope(
                ok=False,
                command="henry.job.cancel",
                status="not_found",
                provider={"type": "henry-background-job"},
                error_obj={"message": f"Job not found: {job_dir}"},
            )
        )
    metadata = read_job_metadata(job_dir)
    state, _ = infer_job_state(job_dir, metadata)
    plan = [{"pid": metadata.get("pid"), "signal": "SIGTERM"}] if metadata.get("pid") else []
    if args.dry_run:
        return emit(
            envelope(
                ok=True,
                command="henry.job.cancel",
                status="dry_run",
                provider={"type": "henry-background-job"},
                outputs=[{"type": "henry_job_cancel_plan", "cancel_plan": plan}],
            )
        )
    if state != "running":
        return emit(
            envelope(
                ok=True,
                command="henry.job.cancel",
                status="already_final",
                provider={"type": "henry-background-job"},
                outputs=[{"type": "henry_job_cancel_plan", "cancel_plan": plan}],
            )
        )
    if metadata.get("pid"):
        try:
            os.kill(int(metadata["pid"]), signal.SIGTERM)
        except OSError:
            pass
    metadata["status"] = "cancelled"
    write_job_metadata(job_dir, metadata)
    return emit(
        envelope(
            ok=True,
            command="henry.job.cancel",
            status="cancelled",
            provider={"type": "henry-background-job"},
            outputs=[{"type": "henry_job_cancel_plan", "cancel_plan": plan}],
        )
    )


def command_job_list(args: argparse.Namespace) -> int:
    jobs_path = job_root(args.jobs_dir or DEFAULT_JOBS_DIR, DEFAULT_JOBS_DIR)
    jobs: list[dict[str, Any]] = []
    if jobs_path.exists():
        for job_dir in sorted(path for path in jobs_path.iterdir() if path.is_dir()):
            job_file = job_dir / "job.json"
            if not job_file.exists():
                continue
            metadata = json.loads(job_file.read_text(encoding="utf-8"))
            jobs.append(
                {
                    "job_id": metadata.get("job_id"),
                    "status": metadata.get("status"),
                    "job_dir": str(job_dir),
                    "created_at": metadata.get("created_at"),
                }
            )
    return emit(
        envelope(
            ok=True,
            command="henry.job.list",
            status="completed",
            provider={"type": "henry-background-job"},
            outputs=[{"type": "henry_job_list", "jobs": jobs}],
        )
    )


def command_job_cleanup(args: argparse.Namespace) -> int:
    jobs_path = job_root(args.jobs_dir or DEFAULT_JOBS_DIR, DEFAULT_JOBS_DIR)
    threshold = parse_duration_seconds(args.older_than)
    removed: list[dict[str, Any]] = []
    now = time.time()
    if jobs_path.exists():
        for job_dir in sorted(path for path in jobs_path.iterdir() if path.is_dir()):
            job_file = job_dir / "job.json"
            if not job_file.exists():
                continue
            metadata = json.loads(job_file.read_text(encoding="utf-8"))
            created_at = metadata.get("created_at")
            if created_at:
                try:
                    created_ts = datetime.fromisoformat(created_at).timestamp()
                except ValueError:
                    created_ts = job_file.stat().st_mtime
            else:
                created_ts = job_file.stat().st_mtime
            if now - created_ts < threshold:
                continue
            removed.append({"job_id": metadata.get("job_id"), "job_dir": str(job_dir)})
            shutil.rmtree(job_dir, ignore_errors=True)
    return emit(
        envelope(
            ok=True,
            command="henry.job.cleanup",
            status="completed",
            provider={"type": "henry-background-job"},
            outputs=[{"type": "henry_job_cleanup", "removed": removed}],
        )
    )


def iter_text_files() -> list[Path]:
    roots = [
        SKILL_ROOT / "README.md",
        SKILL_ROOT / "CHANGELOG.md",
        SKILL_ROOT / "SKILL.md",
        SKILL_ROOT / ".gitattributes",
        SKILL_ROOT / ".gitignore",
        SKILL_ROOT / ".github",
        SKILL_ROOT / "agents",
        SKILL_ROOT / "docs",
        SKILL_ROOT / "references",
        SKILL_ROOT / "scripts",
        SKILL_ROOT / "tests",
    ]
    files: list[Path] = []
    for root in roots:
        if root.is_file():
            files.append(root)
            continue
        if not root.exists():
            continue
        for candidate in root.rglob("*"):
            if candidate.is_file() and candidate.suffix.lower() in TEXT_SUFFIXES:
                files.append(candidate)
    return files


def missing_required_files() -> list[str]:
    required = [
        SKILL_ROOT / "README.md",
        SKILL_ROOT / "CHANGELOG.md",
        SKILL_ROOT / "LICENSE",
        SKILL_ROOT / "SKILL.md",
        AGENT_FILE_PATH,
        SKILL_ROOT / ".github" / "workflows" / "ci.yml",
        SKILL_ROOT / "references" / "api.md",
        SKILL_ROOT / "references" / "quick-card.md",
        SKILL_ROOT / "references" / "routing.md",
        SKILL_ROOT / "references" / "setup.md",
    ]
    return [str(path.relative_to(SKILL_ROOT)) for path in required if not path.exists()]


def disallowed_marker_issues() -> list[str]:
    issues: list[str] = []
    for path in iter_text_files():
        if path.resolve() == Path(__file__).resolve():
            continue
        text = path.read_text(encoding="utf-8")
        for marker in REMOVED_TEXT_MARKERS:
            if marker in text:
                issues.append(f"{path.relative_to(SKILL_ROOT)} contains {marker}")
    return issues


def command_quick_validate(_args: argparse.Namespace) -> int:
    issues: list[str] = []
    missing = missing_required_files()
    if missing:
        issues.extend([f"Missing required file: {item}" for item in missing])
    old_agent = SKILL_ROOT / "agents" / ("open" + "ai.yaml")
    if old_agent.exists():
        issues.append("Legacy agent file is still present.")

    top = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--help"],
        cwd=SKILL_ROOT,
        env=os.environ.copy(),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=30,
    )
    if top.returncode != 0:
        issues.append("Top-level help command failed.")
    help_text = top.stdout
    for marker in (("probe-image-" + "providers"), ("provider-" + "cache")):
        if marker in help_text:
            issues.append(f"Removed command still appears in top-level help: {marker}")

    generate_help = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "generate", "--help"],
        cwd=SKILL_ROOT,
        env=os.environ.copy(),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=30,
    )
    if generate_help.returncode != 0:
        issues.append("Generate help command failed.")
    if ("candidate-" + "policy") in generate_help.stdout:
        issues.append("Removed flag still appears in generate help.")

    issues.extend(disallowed_marker_issues())
    payload = envelope(
        ok=not issues,
        command="henry.quick_validate",
        status="completed" if not issues else "validation_error",
        provider={"type": "henry-local-validator"},
        outputs=[{"type": "henry_validation_results", "issues": issues}],
        metadata={"skill_root": str(SKILL_ROOT), "strict_names": True},
        error_obj=None if not issues else {"message": "Local validation issues were found."},
    )
    return emit(payload)


def command_probe(args: argparse.Namespace) -> int:
    apply_model_env_defaults(args)
    try:
        config = resolve_remote_config(args)
    except ValueError as exc:
        return emit(
            envelope(
                ok=False,
                command="henry.probe",
                status="validation_error",
                provider={"type": "henry-local-validator"},
                error_obj={"message": str(exc)},
            )
        )
    metadata = route_metadata(config, args.route)
    provider = provider_info(config["base_url"], route=args.route, base_url_source=config["base_url_source"])
    if not args.live:
        return emit(
            envelope(
                ok=True,
                command="henry.probe",
                status="environment_ready",
                provider=provider,
                outputs=[{"type": "henry_probe", "live": False}],
                metadata=metadata,
            )
        )
    with tempfile.TemporaryDirectory() as tmp:
        probe_args = clone_args(
            args,
            prompt="connectivity check",
            prompt_file=None,
            dry_run=False,
            force=True,
            out=str(Path(tmp) / "probe.png"),
            background_job=False,
        )
        result = run_image_command_result(command="henry.probe", args=probe_args, out=probe_args.out, persist_on_success=False)
        for output in result.get("outputs", []):
            path = output.get("path")
            manifest = output.get("manifest")
            if path and Path(path).exists():
                Path(path).unlink()
            if manifest and Path(manifest).exists():
                Path(manifest).unlink()
        result["outputs"] = [{"type": "henry_probe", "live": True}]
        return emit(result)


def command_prompt(args: argparse.Namespace) -> int:
    try:
        prompt = read_prompt(args.prompt, args.prompt_file)
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
            parse_size=lambda value: None if value == "auto" else tuple(int(item) for item in value.split("x")),
        )
        return emit(
            envelope(
                ok=True,
                command="henry.prompt",
                status="completed",
                provider={"type": "henry-prompt-package"},
                outputs=[{"type": "henry_prompt_package", "package": package}],
            )
        )
    except ValueError as exc:
        return emit(
            envelope(
                ok=False,
                command="henry.prompt",
                status="validation_error",
                provider={"type": "henry-local-validator"},
                error_obj={"message": str(exc)},
            )
        )


def command_generate(args: argparse.Namespace) -> int:
    if args.background_job:
        return start_background_job("generate", args)
    return emit(run_image_command_result(command="henry.generate", args=args, out=args.out))


def command_edit(args: argparse.Namespace) -> int:
    if args.background_job:
        return start_background_job("edit", args)
    return emit(run_image_command_result(command="henry.edit", args=args, out=args.out))


def command_batch(args: argparse.Namespace) -> int:
    if args.background_job:
        return start_background_job("batch", args)
    input_path = Path(args.batch_input)
    if not input_path.exists():
        return emit(
            envelope(
                ok=False,
                command="henry.batch",
                status="validation_error",
                provider={"type": "henry-local-validator"},
                error_obj={"message": f"Batch input not found: {input_path}"},
            )
        )
    tasks: list[dict[str, Any]] = []
    with input_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                task = json.loads(text)
            except json.JSONDecodeError as exc:
                return emit(
                    envelope(
                        ok=False,
                        command="henry.batch",
                        status="validation_error",
                        provider={"type": "henry-local-validator"},
                        error_obj={"message": f"Invalid JSONL at line {line_number}: {exc}"},
                    )
                )
            tasks.append(task)
    if not tasks:
        return emit(
            envelope(
                ok=False,
                command="henry.batch",
                status="validation_error",
                provider={"type": "henry-local-validator"},
                error_obj={"message": "Batch input contains no tasks."},
            )
        )
    Path(args.out_dir).mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    ok = True
    for index, task in enumerate(tasks, start=1):
        task_args = build_batch_task_args(args, task, index)
        task_command = "henry.batch.edit" if task_args.image or task_args.image_file_id else "henry.batch.generate"
        task_result = run_image_command_result(
            command=task_command,
            args=task_args,
            out=task_args.out,
            source_output=str(input_path),
            persist_on_success=False,
        )
        results.append({"index": index, "result": task_result})
        ok = ok and bool(task_result.get("ok"))
    payload = envelope(
        ok=ok,
        command="henry.batch",
        status="completed" if ok else "partial_failure",
        provider={"type": "henry-batch"},
        outputs=[{"type": "henry_batch_results", "results": results}],
    )
    payload = attach_workflow_metadata(
        payload,
        cache_root=SKILL_CACHE_ROOT,
        args=args,
        command="henry.batch",
        out=args.out_dir,
        source_output=str(input_path),
        persist_on_success=False,
    )
    return emit(payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=f"{HENRY_IMAGE_DISPLAY_NAME} generation helper.")
    parser.add_argument("--version", action="version", version=HENRY_IMAGE_DISPLAY_NAME)

    sub = parser.add_subparsers(dest="subcommand", required=True)

    def add_shared_remote_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--base-url", default=None, help="Remote image service base URL.")
        p.add_argument("--api-key-env", default=None, help="Optional API key environment variable name, checked before HENRY_IMAGE_API_KEY.")
        p.add_argument("--route", default="auto", choices=sorted(ROUTES))
        p.add_argument("--model", default=None)
        p.add_argument("--image-model", default=None)
        p.add_argument("--size", default=DEFAULT_SIZE)
        p.add_argument("--quality", default=DEFAULT_QUALITY, choices=sorted(QUALITIES))
        p.add_argument("--output-format", default=DEFAULT_OUTPUT_FORMAT, choices=sorted(OUTPUT_FORMATS))
        p.add_argument("--images-response-format", default="auto", choices=sorted(IMAGE_RESPONSE_FORMATS))
        p.add_argument("--images-compat", default="auto", choices=sorted(IMAGE_COMPAT_MODES))
        p.add_argument("--input-fidelity", default="auto", choices=sorted(INPUT_FIDELITIES))
        p.add_argument("--background", default="auto", choices=sorted(BACKGROUNDS))
        p.add_argument("--moderation", default="auto", choices=sorted(MODERATIONS))
        p.add_argument("--partial-images", type=int, default=0)
        p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
        p.add_argument("--retries", type=int, default=0)
        p.add_argument("--n", type=int, default=1)
        p.add_argument("--output-compression", type=int, default=None)
        p.add_argument("--force", action="store_true")

    def add_prompt_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--prompt", default=None)
        p.add_argument("--prompt-file", default=None)

    probe = sub.add_parser("probe", help="Validate Henry Image configuration and optionally perform a live connectivity check.")
    add_shared_remote_args(probe)
    probe.add_argument("--live", action="store_true")
    probe.set_defaults(func=command_probe)

    prompt = sub.add_parser("prompt", help="Build a Henry Image prompt package without calling the remote service.")
    add_prompt_args(prompt)
    prompt.add_argument("--size", default=DEFAULT_SIZE)
    prompt.add_argument("--negative-prompt", default="")
    prompt.add_argument("--use-case", default="auto")
    prompt.add_argument("--review-template", default="auto", choices=sorted(REVIEW_TEMPLATES))
    prompt.add_argument("--platform", default="generic", choices=sorted(PROMPT_PLATFORMS))
    prompt.add_argument("--package-version", default="generic", choices=sorted(PROMPT_PACKAGE_VERSIONS))
    prompt.add_argument("--explain", action="store_true")
    prompt.set_defaults(func=command_prompt)

    gen = sub.add_parser("generate", help="Generate a new image and save it locally.")
    add_shared_remote_args(gen)
    add_prompt_args(gen)
    gen.add_argument("--out", default=DEFAULT_OUT)
    gen.add_argument("--background-job", action="store_true")
    gen.add_argument("--dry-run", action="store_true")
    gen.set_defaults(func=command_generate)

    edit = sub.add_parser("edit", help="Edit an image using one or more image inputs.")
    add_shared_remote_args(edit)
    add_prompt_args(edit)
    edit.add_argument("--image", action="append", default=[])
    edit.add_argument("--image-file-id", action="append", default=[])
    edit.add_argument("--mask", default=None)
    edit.add_argument("--mask-file-id", default=None)
    edit.add_argument("--out", default="output/imagegen/henry-image-edit.png")
    edit.add_argument("--background-job", action="store_true")
    edit.add_argument("--dry-run", action="store_true")
    edit.set_defaults(func=command_edit)

    batch = sub.add_parser("batch", help="Run a JSONL batch of generate or edit tasks.")
    add_shared_remote_args(batch)
    batch.add_argument("--batch-input", required=True)
    batch.add_argument("--out-dir", default="output/imagegen/batch")
    batch.add_argument("--background-job", action="store_true")
    batch.add_argument("--negative-prompt", default="")
    batch.add_argument("--use-case", default="auto")
    batch.add_argument("--review-template", default="auto", choices=sorted(REVIEW_TEMPLATES))
    batch.add_argument("--platform", default="generic", choices=sorted(PROMPT_PLATFORMS))
    batch.add_argument("--package-version", default="generic", choices=sorted(PROMPT_PACKAGE_VERSIONS))
    batch.add_argument("--explain", action="store_true")
    batch.add_argument("--prompt", default=None)
    batch.add_argument("--prompt-file", default=None)
    batch.set_defaults(func=command_batch)

    job_status = sub.add_parser("job-status", help="Check a Henry Image background job.")
    job_status.add_argument("--job", required=True)
    job_status.add_argument("--jobs-dir", default=None)
    job_status.add_argument("--watch", action="store_true")
    job_status.add_argument("--interval", type=float, default=DEFAULT_INTERVAL)
    job_status.add_argument("--diagnose", action="store_true")
    job_status.set_defaults(func=command_job_status)

    job_diagnose = sub.add_parser("job-diagnose", help="Summarize a Henry Image background job.")
    job_diagnose.add_argument("--job", required=True)
    job_diagnose.add_argument("--jobs-dir", default=None)
    job_diagnose.add_argument("--format", default="json", choices=("json", "human"))
    job_diagnose.set_defaults(func=command_job_diagnose)

    job_cancel = sub.add_parser("job-cancel", help="Cancel a Henry Image background job.")
    job_cancel.add_argument("--job", required=True)
    job_cancel.add_argument("--jobs-dir", default=None)
    job_cancel.add_argument("--dry-run", action="store_true")
    job_cancel.set_defaults(func=command_job_cancel)

    job_list = sub.add_parser("job-list", help="List Henry Image background jobs.")
    job_list.add_argument("--jobs-dir", default=None)
    job_list.set_defaults(func=command_job_list)

    job_cleanup = sub.add_parser("job-cleanup", help="Remove old Henry Image background jobs.")
    job_cleanup.add_argument("--jobs-dir", default=None)
    job_cleanup.add_argument("--older-than", required=True)
    job_cleanup.set_defaults(func=command_job_cleanup)

    quick = sub.add_parser("quick_validate", help="Run Henry Image local contract checks.")
    quick.set_defaults(func=command_quick_validate)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
