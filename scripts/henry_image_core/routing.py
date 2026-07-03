from __future__ import annotations

from typing import Any
from urllib import parse


def unsupported_responses_result(result: dict[str, Any], classify_api_failure: Any) -> bool:
    if result.get("status") == "no_image_result":
        return True
    error_data = result.get("error") or {}
    category = str(error_data.get("category") or classify_api_failure(error_data)).lower()
    if category in {"invalid_credentials", "missing_credentials", "content_policy", "quota_exceeded", "rate_limited", "bad_parameter"}:
        return False
    code = str(error_data.get("code") or "").lower()
    message = str(error_data.get("message") or "").lower()
    status = error_data.get("status")
    if code in {"invalid_api_key", "missing_openai_api_key", "content_policy"}:
        return False
    if status in {404, 405, 408, 409, 425, 500, 502, 503, 504, None}:
        return True
    return any(token in message for token in ("image_generation", "tool", "responses", "timeout", "no image"))


def unsupported_images_payload_result(result: Any) -> bool:
    error_data = result.error or {}
    status = error_data.get("status")
    if status != 400:
        return False
    code = str(error_data.get("code") or "").lower()
    message = str(error_data.get("message") or "").lower()
    if code in {"invalid_api_key", "missing_openai_api_key", "content_policy"}:
        return False
    field_tokens = (
        "unsupported parameter",
        "unrecognized request argument",
        "unknown parameter",
        "extra fields",
        "not permitted",
        "response_format",
        "quality",
        "background",
        "output_format",
        "output_compression",
        "moderation",
    )
    return any(token in message for token in field_tokens)


def legacy_should_try_next_candidate(result: dict[str, Any]) -> bool:
    if result.get("ok"):
        return False
    if result.get("status") == "validation_error":
        return False
    if result.get("status") in {"missing_credentials", "no_image_result"}:
        return True
    error_data = result.get("error") or {}
    status = error_data.get("status")
    code = str(error_data.get("code") or "").lower()
    message = str(error_data.get("message") or "").lower()
    if status in {401, 403, 404, 405, 408, 409, 425, 429, 500, 502, 503, 504, None}:
        return True
    if code in {"invalid_api_key", "missing_openai_api_key", "url_error", "timeout", "not_found"}:
        return True
    return any(token in message for token in ("unsupported endpoint", "not found", "no image", "image_generation", "responses", "timeout"))


def should_try_next_candidate(result: dict[str, Any], args: Any, classify_api_failure: Any) -> bool:
    if result.get("ok") or result.get("status") == "validation_error":
        return False
    policy = getattr(args, "candidate_policy", "auto") if args is not None else "auto"
    if policy == "strict":
        return False
    if policy == "all":
        return legacy_should_try_next_candidate(result)
    status = result.get("status")
    error_data = result.get("error") or {}
    category = str(error_data.get("category") or classify_api_failure(error_data)).lower()
    if status in {"invalid_credentials", "content_policy", "quota_exceeded", "rate_limited", "bad_parameter"}:
        return False
    if category in {"invalid_credentials", "content_policy", "quota_exceeded", "rate_limited", "bad_parameter"}:
        return False
    return legacy_should_try_next_candidate(result)


def summarize_attempt(result: dict[str, Any], base_url: str, base_url_source: str, route: str) -> dict[str, Any]:
    metadata = result.get("metadata") or {}
    return {
        "base_url_source": base_url_source,
        "base_url_host": parse.urlparse(base_url).netloc or base_url,
        "route": route,
        "ok": result.get("ok"),
        "status": result.get("status"),
        "api_key_env": metadata.get("api_key_env"),
        "api_key_attempts": metadata.get("api_key_attempts"),
        "auth_source": metadata.get("auth_source"),
        "auth_shape": metadata.get("auth_shape"),
        "header_names": metadata.get("header_names"),
        "query_names": metadata.get("query_names"),
        "provider_family": metadata.get("provider_family"),
        "adaptive_reason": metadata.get("adaptive_reason"),
        "auth_attempts": metadata.get("auth_attempts"),
        "payload_mode": metadata.get("payload_mode"),
        "error": result.get("error"),
    }


def is_edit_command(command: str) -> bool:
    return command in {"henry.edit", "henry.batch.edit"} or command.endswith(".edit")
