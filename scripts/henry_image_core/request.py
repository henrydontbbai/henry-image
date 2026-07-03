from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Callable
from urllib import request


def output_paths(out: str, count: int, ext: str, force: bool) -> list[Path]:
    base = Path(out)
    if base.exists() and base.is_dir():
        paths = [base / f"image_{i + 1}.{ext}" for i in range(count)]
    elif "{index}" in str(base):
        paths = [Path(str(base).replace("{index}", str(i + 1))) for i in range(count)]
    elif count == 1:
        paths = [base]
    else:
        stem = base.with_suffix("")
        paths = [Path(f"{stem}-{i + 1}.{ext}") for i in range(count)]
    for path in paths:
        if path.exists() and not force:
            raise ValueError(f"Output already exists: {path}. Use --force to overwrite.")
    return paths


def write_image_bytes(images_raw: list[bytes], out: str, output_format: str, force: bool) -> list[dict[str, Any]]:
    paths = output_paths(out, len(images_raw), output_format, force)
    outputs: list[dict[str, Any]] = []
    for idx, (raw, path) in enumerate(zip(images_raw, paths), start=1):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        if path.stat().st_size == 0:
            raise ValueError(f"Output file is empty: {path}")
        outputs.append({"index": idx, "path": str(path), "bytes": path.stat().st_size, "format": output_format})
    return outputs


def decode_image_b64(value: str) -> bytes:
    if value.startswith("data:image/") and ";base64," in value:
        value = value.split(";base64,", 1)[1]
    return base64.b64decode(value)


def download_image(url: str, timeout: int, *, is_data_image_url: Callable[[str], bool]) -> bytes:
    if is_data_image_url(url):
        return decode_image_b64(url)
    with request.urlopen(url, timeout=timeout) as response:
        return response.read()


def write_images(images_b64: list[str], out: str, output_format: str, force: bool) -> list[dict[str, Any]]:
    return write_image_bytes([decode_image_b64(item) for item in images_b64], out, output_format, force)


def write_manifest(out_path: str, manifest: dict[str, Any], force: bool, *, redact: Callable[[Any], Any]) -> str:
    path = Path(out_path)
    manifest_path = path.with_suffix(path.suffix + ".json") if path.suffix else path / "manifest.json"
    if manifest_path.exists() and not force:
        raise ValueError(f"Manifest already exists: {manifest_path}. Use --force to overwrite.")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(redact(manifest), ensure_ascii=False, indent=2), encoding="utf-8")
    return str(manifest_path)


def parse_error_body(status: int, detail: str) -> dict[str, Any]:
    try:
        body = json.loads(detail)
    except json.JSONDecodeError:
        body = {"message": detail}
    error_data = body.get("error") if isinstance(body, dict) else None
    if not isinstance(error_data, dict):
        error_data = body if isinstance(body, dict) else {"message": str(body)}
    return {
        "status": status,
        "code": error_data.get("code"),
        "type": error_data.get("type"),
        "message": error_data.get("message", "API request failed."),
    }


def classify_api_failure(error_data: dict[str, Any] | None) -> str:
    error_data = error_data or {}
    status = error_data.get("status")
    code = str(error_data.get("code") or "").lower()
    error_type = str(error_data.get("type") or "").lower()
    message = str(error_data.get("message") or "").lower()
    combined = " ".join((code, error_type, message))
    if code in {"invalid_api_key", "incorrect_api_key", "authentication_error"} or status in {401, 403}:
        return "invalid_credentials"
    if "missing_openai_api_key" in combined or "missing api key" in combined:
        return "missing_credentials"
    if "insufficient_quota" in combined:
        return "quota_exceeded"
    if "rate_limit" in combined or status == 429:
        return "rate_limited"
    if "content_policy" in combined or "safety" in combined:
        return "content_policy"
    if "timeout" in combined:
        return "timeout"
    if "url_error" in combined or "network" in combined:
        return "network_error"
    if status == 404 or "not found" in combined:
        return "not_found"
    if status and 400 <= int(status) < 500:
        return "bad_parameter"
    if status and int(status) >= 500:
        return "server_error"
    return "api_error"


def failure_error_obj(error_data: dict[str, Any] | None) -> dict[str, Any]:
    error_data = error_data or {}
    return {
        "status": error_data.get("status"),
        "code": error_data.get("code"),
        "type": error_data.get("type"),
        "message": error_data.get("message", "API request failed."),
        "category": error_data.get("category") or classify_api_failure(error_data),
    }
