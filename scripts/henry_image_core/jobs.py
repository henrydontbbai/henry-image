from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
import uuid


def job_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]


def job_root(jobs_dir: str, default_jobs_dir: str) -> Path:
    return Path(jobs_dir or default_jobs_dir)


def resolve_job_path(job: str, jobs_dir: str | None, default_jobs_dir: str) -> Path:
    raw = Path(job)
    if raw.exists() or raw.is_absolute() or any(sep in job for sep in ("/", "\\")):
        return raw
    return job_root(jobs_dir or default_jobs_dir, default_jobs_dir) / job


def parse_duration_seconds(value: str) -> int:
    match = re.fullmatch(r"([1-9][0-9]*)([smhd])", value.strip().lower())
    if not match:
        raise ValueError("Duration must look like 3600s, 24h, or 7d.")
    amount = int(match.group(1))
    unit = match.group(2)
    factor = {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
    return amount * factor
