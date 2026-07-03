from __future__ import annotations

from typing import Any

from .contracts import AuthProfile


def auth_profile_summary(profile: AuthProfile) -> dict[str, Any]:
    return {
        "auth_source": profile.source,
        "auth_shape": profile.shape,
        "header_names": list(profile.headers.keys()),
        "query_names": list(profile.query.keys()),
        "header_sources": dict(profile.header_sources),
        "query_sources": dict(profile.query_sources),
        "provider_family": profile.provider_family,
        "adaptive_reason": profile.adaptive_reason,
    }


def dedupe_auth_profiles(profiles: list[AuthProfile]) -> list[AuthProfile]:
    deduped: list[AuthProfile] = []
    seen: set[tuple[Any, ...]] = set()
    for profile in profiles:
        fingerprint = (
            profile.shape,
            profile.value,
            tuple(sorted(profile.headers.items())),
            tuple(sorted(profile.query.items())),
        )
        if fingerprint in seen:
            continue
        deduped.append(profile)
        seen.add(fingerprint)
    return deduped
