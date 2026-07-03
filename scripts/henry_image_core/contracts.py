from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ApiResult:
    ok: bool
    status: int | None
    data: dict[str, Any] | None
    error: dict[str, Any] | None
    request_id: str | None
    latency_ms: int


@dataclass
class AuthProfile:
    value: str | None
    source: str
    shape: str
    headers: dict[str, str]
    query: dict[str, str]
    header_sources: dict[str, str]
    query_sources: dict[str, str]
    provider_family: str
    adaptive_reason: str


@dataclass
class ImageTask:
    command: str
    prompt: str
    out: str
    mode: str
    stage: str
    source_output: str | None = None
