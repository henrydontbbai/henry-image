from __future__ import annotations

import base64
import json
import mimetypes
import uuid
from pathlib import Path
from typing import Any, Callable
from urllib import error, request


class NetworkOperationError(Exception):
    def __init__(self, error_data: dict[str, Any]):
        super().__init__(str(error_data.get("message") or "Remote network operation failed."))
        self.error_data = error_data


def transport_error_data(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, error.URLError):
        reason = exc.reason
        if isinstance(reason, TimeoutError):
            message = str(reason) or "The read operation timed out."
            return {"status": None, "code": "timeout", "message": message}
        return {"status": None, "code": "url_error", "message": str(reason)}
    if isinstance(exc, TimeoutError):
        return {"status": None, "code": "timeout", "message": str(exc) or "The read operation timed out."}
    return {"status": None, "code": "network_error", "message": str(exc) or "Remote network operation failed."}


def safe_urlopen(target: Any, timeout: int):
    try:
        return request.urlopen(target, timeout=timeout)
    except error.HTTPError:
        raise
    except error.URLError as exc:
        raise NetworkOperationError(transport_error_data(exc)) from exc
    except TimeoutError as exc:
        raise NetworkOperationError(transport_error_data(exc)) from exc


def read_response_bytes(response: Any) -> bytes:
    try:
        return response.read()
    except error.HTTPError:
        raise
    except error.URLError as exc:
        raise NetworkOperationError(transport_error_data(exc)) from exc
    except TimeoutError as exc:
        raise NetworkOperationError(transport_error_data(exc)) from exc


def http_error_data(exc: error.HTTPError, *, default_message: str) -> dict[str, Any]:
    detail = ""
    try:
        detail = exc.read().decode("utf-8", errors="replace")
    except Exception:
        detail = ""
    parsed = parse_error_body(exc.code, detail or str(exc.reason or exc) or default_message)
    if not parsed.get("message"):
        parsed["message"] = default_message
    return parsed


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
    try:
        with safe_urlopen(url, timeout) as response:
            return read_response_bytes(response)
    except error.HTTPError as exc:
        raise NetworkOperationError(http_error_data(exc, default_message="Remote image download failed.")) from exc


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
        "message": error_data.get("message", "Remote service request failed."),
    }


def request_json(url: str, headers: dict[str, str], payload: dict[str, Any], timeout: int, api_result_type: type) -> Any:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    for key, value in headers.items():
        req.add_header(key, value)
    try:
        with safe_urlopen(req, timeout) as response:
            data = json.loads(read_response_bytes(response).decode("utf-8"))
            return api_result_type(True, response.status, data, None, response.headers.get("x-request-id"), 0)
    except error.HTTPError as exc:
        return api_result_type(False, exc.code, None, http_error_data(exc, default_message="Remote service request failed."), exc.headers.get("x-request-id"), 0)
    except NetworkOperationError as exc:
        return api_result_type(False, None, None, exc.error_data, None, 0)


def build_multipart_body(
    *,
    fields: dict[str, str],
    files: list[tuple[str, str, bytes]],
) -> tuple[bytes, str]:
    boundary = f"henry-image-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )
    for name, filename, raw in files:
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"; filename="{Path(filename).name}"\r\n'.encode("utf-8"),
                f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
                raw,
                b"\r\n",
            ]
        )
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), boundary


def request_multipart(
    url: str,
    headers: dict[str, str],
    fields: dict[str, str],
    files: list[tuple[str, str, bytes]],
    timeout: int,
    api_result_type: type,
) -> Any:
    body, boundary = build_multipart_body(fields=fields, files=files)
    req = request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    for key, value in headers.items():
        req.add_header(key, value)
    try:
        with safe_urlopen(req, timeout) as response:
            data = json.loads(read_response_bytes(response).decode("utf-8"))
            return api_result_type(True, response.status, data, None, response.headers.get("x-request-id"), 0)
    except error.HTTPError as exc:
        return api_result_type(False, exc.code, None, http_error_data(exc, default_message="Remote service request failed."), exc.headers.get("x-request-id"), 0)
    except NetworkOperationError as exc:
        return api_result_type(False, None, None, exc.error_data, None, 0)


def classify_api_failure(error_data: dict[str, Any] | None) -> str:
    error_data = error_data or {}
    status = error_data.get("status")
    code = str(error_data.get("code") or "").lower()
    error_type = str(error_data.get("type") or "").lower()
    message = str(error_data.get("message") or "").lower()
    combined = " ".join((code, error_type, message))
    if status in {401, 403}:
        return "invalid_credentials"
    if "missing" in combined and "key" in combined:
        return "missing_credentials"
    if "quota" in combined:
        return "quota_exceeded"
    if "rate" in combined and "limit" in combined or status == 429:
        return "rate_limited"
    if "policy" in combined or "unsafe" in combined:
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
        "message": error_data.get("message", "Remote service request failed."),
        "category": error_data.get("category") or classify_api_failure(error_data),
    }


def extract_response_images(data: dict[str, Any]) -> list[str]:
    images: list[str] = []
    for item in data.get("output", []):
        if isinstance(item, dict) and item.get("type") == "image_generation_call" and item.get("result"):
            images.append(str(item["result"]))
        for content in item.get("content", []) if isinstance(item, dict) else []:
            if isinstance(content, dict) and content.get("image_base64"):
                images.append(str(content["image_base64"]))
    for item in data.get("data", []):
        if isinstance(item, dict) and item.get("b64_json"):
            images.append(str(item["b64_json"]))
    return images


def extract_images_api_images(
    data: dict[str, Any],
    *,
    timeout: int,
    is_data_image_url: Callable[[str], bool],
) -> list[bytes]:
    images: list[bytes] = []
    for item in data.get("data", []):
        if not isinstance(item, dict):
            continue
        if item.get("b64_json"):
            images.append(decode_image_b64(str(item["b64_json"])))
        elif item.get("url"):
            images.append(download_image(str(item["url"]), timeout, is_data_image_url=is_data_image_url))
    return images
