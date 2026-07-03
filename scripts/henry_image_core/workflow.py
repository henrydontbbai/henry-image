from __future__ import annotations

import json
from pathlib import Path
import shlex
from typing import Any


WORKFLOW_PROFILE_VERSION = 1


def workflow_profile_path(cache_root: Path) -> Path:
    return cache_root / "workflow-profile.json"


def load_workflow_profile(cache_root: Path) -> dict[str, Any]:
    path = workflow_profile_path(cache_root)
    if not path.exists():
        return {"version": WORKFLOW_PROFILE_VERSION}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"version": WORKFLOW_PROFILE_VERSION}
    if not isinstance(data, dict):
        return {"version": WORKFLOW_PROFILE_VERSION}
    data.setdefault("version", WORKFLOW_PROFILE_VERSION)
    return data


def update_workflow_profile(
    cache_root: Path,
    *,
    mode: str,
    out: str,
    size: str | None = None,
    quality: str | None = None,
    output_format: str | None = None,
    route: str | None = None,
    provider: str | None = None,
) -> dict[str, Any]:
    profile = load_workflow_profile(cache_root)
    profile.update(
        {
            "version": WORKFLOW_PROFILE_VERSION,
            "last_mode": mode,
            "default_output_dir": str(Path(out).parent),
        }
    )
    if size:
        profile["default_size"] = size
    if quality:
        profile["default_quality"] = quality
    if output_format:
        profile["default_output_format"] = output_format
    if route:
        profile["last_route"] = route
    if provider:
        profile["last_provider"] = provider
    path = workflow_profile_path(cache_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    return profile


def infer_workflow_mode(command: str) -> str:
    if "batch" in command:
        return "batch"
    if command.endswith(".edit") or command == "henry.edit":
        return "edit"
    if command.endswith(".prompt") or command == "henry.prompt":
        return "prompt"
    if "probe" in command:
        return "probe"
    return "generate"


def infer_workflow_stage(ok: bool, status: str, *, dry_run: bool = False) -> str:
    if dry_run or status == "dry_run":
        return "preview"
    if ok:
        return "review"
    if status in {"validation_error", "missing_credentials", "invalid_credentials", "missing_configuration"}:
        return "setup"
    if status in {"rate_limited", "quota_exceeded", "service_unavailable", "no_image_result"}:
        return "recover"
    return "retry"


def build_replay_command(args: Any, out: str, command_name: str) -> str:
    parts = ["python", "scripts/henry_image.py", command_name]
    prompt = getattr(args, "prompt", None)
    prompt_file = getattr(args, "prompt_file", None)
    if prompt:
        parts.extend(["--prompt", prompt])
    elif prompt_file:
        parts.extend(["--prompt-file", prompt_file])
    for field in ("image", "image_file_id"):
        values = getattr(args, field, None) or []
        for value in values:
            parts.extend([f"--{field.replace('_', '-')}", str(value)])
    for field in ("mask", "mask_file_id"):
        value = getattr(args, field, None)
        if value:
            parts.extend([f"--{field.replace('_', '-')}", str(value)])
    for field in ("size", "quality", "route", "model", "image_model", "output_format", "base_url", "api_key_env"):
        value = getattr(args, field, None)
        if value:
            parts.extend([f"--{field.replace('_', '-')}", str(value)])
    if out:
        if command_name == "batch":
            parts.extend(["--out-dir", out])
        else:
            parts.extend(["--out", out])
    return " ".join(shlex.quote(part) for part in parts)


def next_action_for_result(
    *,
    ok: bool,
    status: str,
    mode: str,
    command_name: str,
    replay_command: str,
) -> str:
    if ok:
        if mode == "batch":
            return "Review the batch results and rerun only failed items if needed."
        if mode == "edit":
            return "Review the edited image and continue from this output if another revision is needed."
        return "Review the generated image and reuse this command as the starting point for the next variation."
    if status in {"missing_credentials", "invalid_credentials", "missing_configuration"}:
        return "Set the Henry Image configuration locally, then rerun the same command."
    if status == "service_unavailable":
        return "Check the remote image service status, then retry when the configured route is available."
    if status in {"rate_limited", "quota_exceeded"}:
        return "Wait for service recovery, then rerun the same command."
    if command_name == "batch":
        return "Fix the failed task input or settings, then rerun the batch."
    return f"Fix the blocker and rerun: {replay_command}"


def attach_workflow_metadata(
    result: dict[str, Any],
    *,
    cache_root: Path,
    args: Any,
    command: str,
    out: str,
    source_output: str | None = None,
    persist_on_success: bool = True,
) -> dict[str, Any]:
    metadata = result.setdefault("metadata", {})
    mode = infer_workflow_mode(command)
    command_name = command.split(".")[-1]
    replay_command = build_replay_command(args, out, command_name)
    stage = infer_workflow_stage(
        bool(result.get("ok")),
        str(result.get("status") or ""),
        dry_run=bool(getattr(args, "dry_run", False)),
    )
    workflow = {
        "mode": mode,
        "stage": stage,
        "replay_command": replay_command,
        "source_output": source_output,
        "next_action": next_action_for_result(
            ok=bool(result.get("ok")),
            status=str(result.get("status") or ""),
            mode=mode,
            command_name=command_name,
            replay_command=replay_command,
        ),
    }
    metadata["workflow"] = workflow
    metadata.setdefault("next_action", workflow["next_action"])
    metadata.setdefault("replay_command", workflow["replay_command"])
    if result.get("ok") and persist_on_success and str(result.get("status")) not in {"dry_run", "skipped"}:
        provider = (result.get("provider") or {}).get("base_url_source") or (result.get("provider") or {}).get("type")
        profile = update_workflow_profile(
            cache_root,
            mode=mode,
            out=out,
            size=getattr(args, "size", None),
            quality=getattr(args, "quality", None),
            output_format=getattr(args, "output_format", None),
            route=getattr(args, "route", None),
            provider=str(provider) if provider else None,
        )
        metadata["workflow_profile"] = profile
    else:
        metadata["workflow_profile"] = load_workflow_profile(cache_root)
    return result
