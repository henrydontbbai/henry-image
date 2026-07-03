from __future__ import annotations

import re
from urllib import parse


def is_local_base_url(base_url: str) -> bool:
    host = parse.urlparse(base_url).hostname or ""
    return host.lower() in {"localhost", "127.0.0.1", "::1"}


def is_azure_like(base_url: str, base_url_source: str | None = None) -> bool:
    combined = f"{base_url} {base_url_source or ''}".lower()
    return any(token in combined for token in ("azure", "aoai", "openai.azure.com", "cognitiveservices.azure.com"))


def azure_openai_v1_like(base_url: str) -> bool:
    parsed = parse.urlparse(base_url)
    return bool(re.search(r"/openai/v1/?$", parsed.path or "", re.IGNORECASE))


def provider_family(base_url: str, base_url_source: str | None = None) -> str:
    if is_local_base_url(base_url):
        return "local_relay"
    if is_azure_like(base_url, base_url_source):
        return "azure"
    host = (parse.urlparse(base_url).netloc or base_url).lower()
    if "api.openai.com" in host:
        return "openai"
    return "openai-compatible"
