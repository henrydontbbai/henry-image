from __future__ import annotations

import base64
import binascii
import functools
import http.client
import ipaddress
import json
import mimetypes
import os
import socket
import uuid
from pathlib import Path
from typing import Any, Callable
from urllib import error, parse, request

from henry_image_core.version import API_USER_AGENT


MAX_API_RESPONSE_BYTES = 16 * 1024 * 1024
MAX_IMAGE_RESPONSE_BYTES = 64 * 1024 * 1024
MAX_ERROR_RESPONSE_BYTES = 1024 * 1024


class NetworkOperationError(Exception):
    def __init__(self, error_data: dict[str, Any]):
        super().__init__(str(error_data.get("message") or "Remote network operation failed."))
        self.error_data = error_data


class ImageFormatError(ValueError):
    pass


class InvalidResponseDataError(ValueError):
    pass


def validation_network_error(code: str, message: str) -> NetworkOperationError:
    return NetworkOperationError(
        {
            "status": None,
            "code": code,
            "message": message,
            "category": "validation_error",
        }
    )


def effective_origin(value: str) -> tuple[str, str, int | None] | None:
    try:
        parsed = parse.urlsplit(value)
        port = parsed.port
    except ValueError:
        return None
    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()
    if not scheme or not hostname:
        return None
    if port is None:
        port = 443 if scheme == "https" else 80 if scheme == "http" else None
    return scheme, hostname, port


def same_origin(left: str, right: str) -> bool:
    left_origin = effective_origin(left)
    return left_origin is not None and left_origin == effective_origin(right)


def resolve_public_image_url(url: str) -> tuple[str, int, str]:
    try:
        parsed = parse.urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise validation_network_error(
            "unsafe_image_url",
            "Image URL must be a valid HTTP(S) URL.",
        ) from exc
    scheme = parsed.scheme.lower()
    hostname = parsed.hostname
    if scheme not in {"http", "https"} or not hostname or parsed.username or parsed.password:
        raise validation_network_error(
            "unsafe_image_url",
            "Image URL must use HTTP(S) with a hostname and no userinfo.",
        )
    if port is None:
        port = 443 if scheme == "https" else 80

    try:
        addresses = [ipaddress.ip_address(hostname)]
    except ValueError:
        try:
            records = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise validation_network_error(
                "unsafe_image_url",
                "Image URL hostname could not be resolved safely.",
            ) from exc
        addresses = []
        for family, _socket_type, _protocol, _canonical_name, sockaddr in records:
            if family not in {socket.AF_INET, socket.AF_INET6}:
                continue
            try:
                addresses.append(ipaddress.ip_address(sockaddr[0]))
            except ValueError as exc:
                raise validation_network_error(
                    "unsafe_image_url",
                    "Image URL hostname resolved to an invalid address.",
                ) from exc

    if not addresses:
        raise validation_network_error(
            "unsafe_image_url",
            "Image URL hostname did not resolve to a usable address.",
        )

    for address in addresses:
        effective_address = getattr(address, "ipv4_mapped", None) or address
        if not effective_address.is_global:
            raise validation_network_error(
                "unsafe_image_url",
                "Image URL hostname resolved to a non-public address.",
            )
    return hostname, port, str(addresses[0])


class _ValidatedImageConnection:
    def __init__(self, *args: Any, connect_host: str, **kwargs: Any):
        self._image_connect_host = connect_host
        super().__init__(*args, **kwargs)

    def _connect_validated_socket(self) -> None:
        address = ipaddress.ip_address(self._image_connect_host)
        family = socket.AF_INET6 if address.version == 6 else socket.AF_INET
        destination: tuple[Any, ...]
        if family == socket.AF_INET6:
            destination = (self._image_connect_host, self.port, 0, 0)
        else:
            destination = (self._image_connect_host, self.port)
        sock = socket.socket(family, socket.SOCK_STREAM)
        try:
            sock.settimeout(self.timeout)
            if self.source_address:
                sock.bind(self.source_address)
            sock.connect(destination)
        except OSError:
            sock.close()
            raise
        self.sock = sock
        try:
            self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        if self._tunnel_host:
            self._tunnel()


class ValidatedImageHTTPConnection(_ValidatedImageConnection, http.client.HTTPConnection):
    def connect(self) -> None:
        self._connect_validated_socket()


class ValidatedImageHTTPSConnection(_ValidatedImageConnection, http.client.HTTPSConnection):
    def connect(self) -> None:
        self._connect_validated_socket()
        server_hostname = self._tunnel_host or self.host
        self.sock = self._context.wrap_socket(self.sock, server_hostname=server_hostname)


class SafeImageHTTPHandler(request.HTTPHandler):
    def http_open(self, req: request.Request):
        _hostname, _port, connect_host = resolve_public_image_url(req.full_url)
        connection_factory = functools.partial(ValidatedImageHTTPConnection, connect_host=connect_host)
        return self.do_open(connection_factory, req)


class SafeImageHTTPSHandler(request.HTTPSHandler):
    def https_open(self, req: request.Request):
        _hostname, _port, connect_host = resolve_public_image_url(req.full_url)
        connection_factory = functools.partial(ValidatedImageHTTPSConnection, connect_host=connect_host)
        return self.do_open(connection_factory, req, context=self._context)


class SafeRedirectHandler(request.HTTPRedirectHandler):
    def __init__(self, policy: str):
        super().__init__()
        self.policy = policy

    def redirect_request(
        self,
        req: request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> request.Request | None:
        del fp, msg, headers
        error_code = "unsafe_redirect" if self.policy == "api" else "unsafe_image_url"
        try:
            source = parse.urlsplit(req.full_url)
            target = parse.urlsplit(newurl)
        except ValueError as exc:
            raise validation_network_error(
                error_code,
                "Redirect was rejected because it was not a valid URL.",
            ) from exc
        if self.policy == "api":
            if not same_origin(req.full_url, newurl):
                raise validation_network_error(
                    "unsafe_redirect",
                    "API redirect was rejected because it changed origin.",
                )
        elif self.policy == "image":
            try:
                target.port
            except ValueError as exc:
                raise validation_network_error(
                    "unsafe_image_url",
                    "Image redirect was rejected because it was not a valid HTTP(S) URL.",
                ) from exc
            if target.scheme.lower() not in {"http", "https"} or not target.hostname:
                raise validation_network_error(
                    "unsafe_image_url",
                    "Image redirect was rejected because it did not use HTTP(S).",
                )
            if source.scheme.lower() == "https" and target.scheme.lower() != "https":
                raise validation_network_error(
                    "unsafe_image_url",
                    "Image redirect was rejected because it downgraded HTTPS.",
                )
            resolve_public_image_url(newurl)
        else:
            raise ValueError(f"Unknown redirect policy: {self.policy}")

        method = req.get_method()
        data = req.data
        request_headers = dict(req.header_items())
        if self.policy == "image" and not same_origin(req.full_url, newurl):
            request_headers = {
                key: value
                for key, value in request_headers.items()
                if key.lower() not in {"authorization", "cookie", "proxy-authorization"}
            }
        if code in {301, 302, 303} and method not in {"GET", "HEAD"}:
            method = "GET"
            data = None
            request_headers = {
                key: value
                for key, value in request_headers.items()
                if key.lower() not in {"content-length", "content-type"}
            }
        elif code not in {301, 302, 303, 307, 308}:
            return None
        try:
            return request.Request(
                newurl,
                data=data,
                headers=request_headers,
                method=method,
                origin_req_host=req.origin_req_host,
                unverifiable=True,
            )
        except ValueError as exc:
            raise validation_network_error(
                error_code,
                "Redirect was rejected because it was not a valid URL.",
            ) from exc


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


def safe_urlopen(target: Any, timeout: int, *, policy: str | None = None):
    try:
        if policy is None:
            return request.urlopen(target, timeout=timeout)
        if policy == "image":
            opener = request.build_opener(
                request.ProxyHandler({}),
                SafeRedirectHandler(policy),
                SafeImageHTTPHandler(),
                SafeImageHTTPSHandler(),
            )
        else:
            opener = request.build_opener(SafeRedirectHandler(policy))
        return opener.open(target, timeout=timeout)
    except error.HTTPError:
        raise
    except error.URLError as exc:
        raise NetworkOperationError(transport_error_data(exc)) from exc
    except TimeoutError as exc:
        raise NetworkOperationError(transport_error_data(exc)) from exc


def read_response_bytes(response: Any, *, max_bytes: int = MAX_API_RESPONSE_BYTES) -> bytes:
    try:
        raw = response.read(max_bytes + 1)
    except error.HTTPError:
        raise
    except error.URLError as exc:
        raise NetworkOperationError(transport_error_data(exc)) from exc
    except TimeoutError as exc:
        raise NetworkOperationError(transport_error_data(exc)) from exc
    if len(raw) > max_bytes:
        raise validation_network_error(
            "response_too_large",
            f"Remote response exceeded the {max_bytes}-byte safety limit.",
        )
    return raw


def http_error_data(exc: error.HTTPError, *, default_message: str) -> dict[str, Any]:
    detail = ""
    try:
        detail = exc.read(MAX_ERROR_RESPONSE_BYTES).decode("utf-8", errors="replace")
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


def detect_image_format(raw: bytes) -> str | None:
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if raw.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if len(raw) >= 12 and raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
        return "webp"
    return None


def validate_image_format(raw: bytes, output_format: str) -> None:
    expected = "jpeg" if output_format.lower() in {"jpg", "jpeg"} else output_format.lower()
    actual = detect_image_format(raw)
    if actual != expected:
        actual_label = actual or "unknown"
        raise ImageFormatError(
            f"Remote image format is {actual_label}, expected {expected}."
        )


def write_image_bytes(images_raw: list[bytes], out: str, output_format: str, force: bool) -> list[dict[str, Any]]:
    for raw in images_raw:
        validate_image_format(raw, output_format)
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
    try:
        return base64.b64decode("".join(value.split()), validate=True)
    except binascii.Error as exc:
        raise ValueError("Invalid inline image data. Check the base64 content.") from exc


def download_image(url: str, timeout: int, *, is_data_image_url: Callable[[str], bool]) -> bytes:
    if is_data_image_url(url):
        return decode_image_b64(url)
    resolve_public_image_url(url)
    try:
        with safe_urlopen(url, timeout, policy="image") as response:
            return read_response_bytes(response, max_bytes=MAX_IMAGE_RESPONSE_BYTES)
    except error.HTTPError as exc:
        raise NetworkOperationError(http_error_data(exc, default_message="Remote image download failed.")) from exc


def write_images(images_b64: list[str], out: str, output_format: str, force: bool) -> list[dict[str, Any]]:
    return write_image_bytes([decode_image_b64(item) for item in images_b64], out, output_format, force)


def manifest_path_for_output(out_path: str) -> Path:
    path = Path(out_path)
    if path.exists() and path.is_dir():
        return path / "manifest.json"
    return path.with_suffix(path.suffix + ".json")


def write_manifest(out_path: str, manifest: dict[str, Any], force: bool, *, redact: Callable[[Any], Any]) -> str:
    manifest_path = manifest_path_for_output(out_path)
    if manifest_path.exists() and not force:
        raise ValueError(f"Manifest already exists: {manifest_path}. Use --force to overwrite.")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(redact(manifest), ensure_ascii=False, indent=2), encoding="utf-8")
    return str(manifest_path)


def validate_output_target(target: Path) -> None:
    if target.is_symlink() or (target.exists() and not target.is_file()):
        raise ValueError(f"Output target must be a regular file: {target}")


def write_output_bundle(
    images_raw: list[bytes],
    out: str,
    output_format: str,
    force: bool,
    *,
    manifest_factory: Callable[[list[dict[str, Any]]], dict[str, Any]],
    redact: Callable[[Any], Any],
) -> tuple[list[dict[str, Any]], str]:
    for raw in images_raw:
        validate_image_format(raw, output_format)

    image_paths = output_paths(out, len(images_raw), output_format, force)
    manifest_path = manifest_path_for_output(out)
    if manifest_path.exists() and not force:
        raise ValueError(f"Manifest already exists: {manifest_path}. Use --force to overwrite.")

    outputs = [
        {
            "index": index,
            "path": str(path),
            "bytes": len(raw),
            "format": output_format,
        }
        for index, (raw, path) in enumerate(zip(images_raw, image_paths), start=1)
    ]
    manifest_raw = json.dumps(
        redact(manifest_factory(outputs)),
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")
    targets = [*image_paths, manifest_path]
    payloads = [*images_raw, manifest_raw]
    for target in targets:
        validate_output_target(target)
    token = uuid.uuid4().hex
    staged = [path.with_name(f"{path.name}.tmp-{token}") for path in targets]
    backups = [path.with_name(f"{path.name}.bak-{token}") for path in targets]
    backed_up: list[tuple[Path, Path]] = []
    committed: list[Path] = []
    restore_failed: set[Path] = set()
    restore_errors: list[str] = []

    try:
        for path, raw in zip(staged, payloads):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            if path.stat().st_size == 0:
                raise ValueError(f"Output file is empty: {path}")
        if force:
            for target, backup in zip(targets, backups):
                if target.exists():
                    os.replace(target, backup)
                    backed_up.append((target, backup))
        for temp_path, target in zip(staged, targets):
            os.replace(temp_path, target)
            committed.append(target)
    except Exception as exc:
        backup_targets = {target for target, _backup in backed_up}
        for target in reversed(committed):
            if target not in backup_targets:
                try:
                    target.unlink(missing_ok=True)
                except OSError:
                    pass
        for target, backup in reversed(backed_up):
            try:
                os.replace(backup, target)
            except OSError as restore_exc:
                restore_failed.add(backup)
                restore_errors.append(f"{backup}: {restore_exc}")
        if restore_errors:
            raise OSError(
                f"{exc} Rollback could not restore backup files: {'; '.join(restore_errors)}"
            ) from exc
        raise
    finally:
        for path in [*staged, *(path for path in backups if path not in restore_failed)]:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

    return outputs, str(manifest_path)


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


def invalid_response_result(response: Any, api_result_type: type) -> Any:
    request_id = response.headers.get("x-request-id")
    try:
        data = json.loads(read_response_bytes(response).decode("utf-8"))
    except NetworkOperationError as exc:
        return api_result_type(False, response.status, None, exc.error_data, request_id, 0)
    except (UnicodeDecodeError, json.JSONDecodeError):
        data = None
    if isinstance(data, dict):
        return api_result_type(True, response.status, data, None, request_id, 0)
    return api_result_type(
        False,
        response.status,
        None,
        {
            "status": response.status,
            "code": "invalid_response_data",
            "type": "invalid_response_data",
            "message": "Remote service returned invalid JSON object response data.",
            "category": "validation_error",
        },
        request_id,
        0,
    )


def request_json(url: str, headers: dict[str, str], payload: dict[str, Any], timeout: int, api_result_type: type) -> Any:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", API_USER_AGENT)
    for key, value in headers.items():
        req.add_header(key, value)
    try:
        with safe_urlopen(req, timeout, policy="api") as response:
            return invalid_response_result(response, api_result_type)
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
    req.add_header("User-Agent", API_USER_AGENT)
    for key, value in headers.items():
        req.add_header(key, value)
    try:
        with safe_urlopen(req, timeout, policy="api") as response:
            return invalid_response_result(response, api_result_type)
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
    if "timeout" in combined or "timed out" in combined:
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


def response_list_field(data: dict[str, Any], field: str) -> list[Any]:
    if field not in data:
        return []
    value = data[field]
    if not isinstance(value, list):
        raise InvalidResponseDataError(f"Remote response field {field!r} must be a list.")
    return value


def extract_response_images(data: dict[str, Any]) -> list[str]:
    images: list[str] = []
    for item in response_list_field(data, "output"):
        if not isinstance(item, dict):
            raise InvalidResponseDataError("Remote response output items must be objects.")
        if item.get("type") == "image_generation_call" and item.get("result"):
            images.append(str(item["result"]))
        for content in response_list_field(item, "content"):
            if isinstance(content, dict) and content.get("image_base64"):
                images.append(str(content["image_base64"]))
            elif not isinstance(content, dict):
                raise InvalidResponseDataError("Remote response content items must be objects.")
    for item in response_list_field(data, "data"):
        if not isinstance(item, dict):
            raise InvalidResponseDataError("Remote response data items must be objects.")
        if item.get("b64_json"):
            images.append(str(item["b64_json"]))
    return images


def extract_images_api_images(
    data: dict[str, Any],
    *,
    timeout: int,
    is_data_image_url: Callable[[str], bool],
) -> list[bytes]:
    images: list[bytes] = []
    for item in response_list_field(data, "data"):
        if not isinstance(item, dict):
            raise InvalidResponseDataError("Remote response data items must be objects.")
        if item.get("b64_json"):
            images.append(decode_image_b64(str(item["b64_json"])))
        elif item.get("url"):
            images.append(download_image(str(item["url"]), timeout, is_data_image_url=is_data_image_url))
    return images
