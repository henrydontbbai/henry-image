import json
import tempfile
from pathlib import Path

from helpers import run_cli


def write_job(
    root: Path,
    *,
    job_id: str = "job-test",
    job_status: str = "failed",
    stdout_payload: dict | None = None,
    stderr_lines: list[dict] | None = None,
    extra_metadata: dict | None = None,
) -> Path:
    job_dir = root / job_id
    job_dir.mkdir(parents=True)
    stdout_path = job_dir / "stdout.json"
    stderr_path = job_dir / "stderr.jsonl"
    if stdout_payload is None:
        stdout_path.write_text("", encoding="utf-8")
    else:
        stdout_path.write_text(json.dumps(stdout_payload, ensure_ascii=False), encoding="utf-8")
    stderr_path.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in (stderr_lines or [])),
        encoding="utf-8",
    )
    metadata = {
        "job_id": job_id,
        "status": job_status,
        "command": "henry.generate",
        "pid": 0,
        "created_at": "2026-07-04T00:00:00+00:00",
        "started_at": "2026-07-04T00:00:01+00:00",
        "job_path": str(job_dir),
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
        "out": str(job_dir / "out.png"),
        **(extra_metadata or {}),
    }
    (job_dir / "job.json").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    return job_dir


def failed_payload() -> dict:
    return {
        "ok": False,
        "status": "rate_limited",
        "command": "henry.generate",
        "provider": {"type": "henry-remote-service"},
        "request_id": "req-rate",
        "outputs": [],
        "error": {
            "status": 429,
            "code": "rate_limited",
            "message": "remote service temporarily rate limited",
            "category": "rate_limited",
        },
        "metadata": {
            "route": "responses",
            "auth_source": "HENRY_IMAGE_API_KEY",
            "base_url_source": "HENRY_IMAGE_BASE_URL",
        },
    }


def test_job_diagnose_json_summarizes_failed_job():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        job_dir = write_job(root, stdout_payload=failed_payload())
        proc = run_cli(["job-diagnose", "--job", str(job_dir), "--format", "json"], root)
        assert proc.returncode == 0, proc.stderr + proc.stdout
        payload = json.loads(proc.stdout)
        diagnosis = payload["outputs"][0]["diagnosis"]
        assert payload["command"] == "henry.job.diagnose"
        assert diagnosis["category"] == "rate_limited"
        assert diagnosis["next_action"]
        assert diagnosis["evidence"]


def test_job_diagnose_human_contains_actionable_sections():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        job_dir = write_job(root, stdout_payload=failed_payload())
        proc = run_cli(["job-diagnose", "--job", str(job_dir), "--format", "human"], root)
        assert proc.returncode == 0, proc.stderr + proc.stdout
        assert "Blocker" in proc.stdout
        assert "Evidence" in proc.stdout
        assert "Next action" in proc.stdout


def test_job_status_includes_diagnosis_only_when_requested():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        job_dir = write_job(root, stdout_payload=failed_payload())

        plain = run_cli(["job-status", "--job", str(job_dir)], root)
        assert plain.returncode == 0, plain.stderr + plain.stdout
        plain_payload = json.loads(plain.stdout)
        assert "diagnosis" not in plain_payload["outputs"][0]

        diagnosed = run_cli(["job-status", "--job", str(job_dir), "--diagnose"], root)
        assert diagnosed.returncode == 0, diagnosed.stderr + diagnosed.stdout
        diagnosed_payload = json.loads(diagnosed.stdout)
        assert diagnosed_payload["outputs"][0]["diagnosis"]["category"] == "rate_limited"


def test_job_cancel_dry_run_does_not_modify_files():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        job_dir = write_job(root, job_status="running", extra_metadata={"pid": 111})
        before_job = (job_dir / "job.json").read_text(encoding="utf-8")
        before_stdout = (job_dir / "stdout.json").read_text(encoding="utf-8")
        proc = run_cli(["job-cancel", "--job", str(job_dir), "--dry-run"], root)
        assert proc.returncode == 0, proc.stderr + proc.stdout
        payload = json.loads(proc.stdout)
        assert payload["status"] == "dry_run"
        assert (job_dir / "job.json").read_text(encoding="utf-8") == before_job
        assert (job_dir / "stdout.json").read_text(encoding="utf-8") == before_stdout


def test_job_list_and_cleanup_work():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        jobs_dir = root / "jobs"
        old = write_job(jobs_dir, job_id="old-job")
        new = write_job(jobs_dir, job_id="new-job")
        old_job = json.loads((old / "job.json").read_text(encoding="utf-8"))
        old_job["created_at"] = "2020-01-01T00:00:00+00:00"
        (old / "job.json").write_text(json.dumps(old_job, ensure_ascii=False), encoding="utf-8")

        listed = run_cli(["job-list", "--jobs-dir", str(jobs_dir)], root)
        assert listed.returncode == 0, listed.stderr + listed.stdout
        items = json.loads(listed.stdout)["outputs"][0]["jobs"]
        assert {item["job_id"] for item in items} == {"old-job", "new-job"}

        cleanup = run_cli(["job-cleanup", "--jobs-dir", str(jobs_dir), "--older-than", "365d"], root)
        assert cleanup.returncode == 0, cleanup.stderr + cleanup.stdout
        removed = json.loads(cleanup.stdout)["outputs"][0]["removed"]
        assert any(item["job_id"] == "old-job" for item in removed)
        assert not old.exists()
        assert new.exists()
