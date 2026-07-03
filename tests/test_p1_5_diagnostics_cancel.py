import argparse
import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "henry_image.py"


def load_module():
    spec = importlib.util.spec_from_file_location("henry_image_p1_5_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_cli(args, cwd):
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd, text=True, capture_output=True, timeout=30)


@contextlib.contextmanager
def patched(obj, name, value):
    old = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield
    finally:
        setattr(obj, name, old)


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
        "command": "henry.job.generate",
        "pid": 0,
        "runner_pid": 0,
        "child_pid": 0,
        "created_at": "2026-06-08T00:00:00+00:00",
        "started_at": "2026-06-08T00:00:01+00:00",
        "job_path": str(job_dir),
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
        "out": str(job_dir / "out.png"),
        **(extra_metadata or {}),
    }
    (job_dir / "job.json").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    return job_dir


def rate_limited_payload() -> dict:
    return {
        "ok": False,
        "status": "rate_limited",
        "command": "henry.generate",
        "provider": {"type": "fake"},
        "request_id": "req-rate",
        "outputs": [],
        "error": {
            "status": 429,
            "code": "rate_limit_exceeded",
            "message": "rate limited Bearer sk-" + ("x" * 40),
            "category": "rate_limited",
        },
        "metadata": {
            "candidate_attempts": [
                {
                    "route": "responses",
                    "status": "rate_limited",
                    "base_url_source": "cli",
                    "auth_source": "env:OPENAI_API_KEY",
                    "request_id": "req-rate",
                    "latency_ms": 123,
                    "error": {"code": "rate_limit_exceeded", "message": "sk-" + ("y" * 40)},
                }
            ]
        },
    }


def test_job_diagnose_json_summarizes_failed_job_and_redacts():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        job_dir = write_job(root, stdout_payload=rate_limited_payload())
        proc = run_cli(["job-diagnose", "--job", str(job_dir), "--format", "json"], root)
        assert proc.returncode == 0, proc.stderr + proc.stdout
        envelope = json.loads(proc.stdout)
        diagnosis = envelope["outputs"][0]["diagnosis"]
        assert envelope["command"] == "henry.job.diagnose"
        assert diagnosis["category"] == "rate_limited"
        assert diagnosis["next_action"]
        assert diagnosis["evidence"]
        assert diagnosis["attempts"]
        assert "sk-" not in proc.stdout
        assert "[REDACTED_SECRET]" in proc.stdout


def test_job_diagnose_human_contains_actionable_sections_and_redacts():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        job_dir = write_job(root, stdout_payload=rate_limited_payload())
        proc = run_cli(["job-diagnose", "--job", str(job_dir), "--format", "human"], root)
        assert proc.returncode == 0, proc.stderr + proc.stdout
        assert "Blocker" in proc.stdout
        assert "Evidence" in proc.stdout
        assert "Next action" in proc.stdout
        assert str(job_dir) in proc.stdout
        assert "sk-" not in proc.stdout


def test_job_status_diagnose_keeps_default_compatible_and_adds_diagnosis_when_requested():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        job_dir = write_job(root, stdout_payload=rate_limited_payload())
        plain = run_cli(["job-status", "--job", str(job_dir)], root)
        assert plain.returncode == 0, plain.stderr + plain.stdout
        plain_envelope = json.loads(plain.stdout)
        assert "diagnosis" not in plain_envelope["outputs"][0]

        diagnosed = run_cli(["job-status", "--job", str(job_dir), "--diagnose"], root)
        assert diagnosed.returncode == 0, diagnosed.stderr + diagnosed.stdout
        diagnosed_envelope = json.loads(diagnosed.stdout)
        assert diagnosed_envelope["command"] == "henry.job.status"
        assert diagnosed_envelope["outputs"][0]["diagnosis"]["category"] == "rate_limited"


def test_job_status_diagnose_redacts_nested_result_outputs():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        secret = "sk-" + ("z" * 40)
        job_dir = write_job(
            root,
            stdout_payload={
                "ok": False,
                "status": "rate_limited",
                "command": "henry.generate",
                "provider": {"type": "fake"},
                "outputs": [
                    {
                        "type": "debug",
                        "headers": {
                            "Authorization": f"Bearer {secret}",
                            "api-key": "azure-secret-value",
                        },
                    }
                ],
                "error": {
                    "status": 429,
                    "code": "rate_limit_exceeded",
                    "message": f"rate limited Authorization: Bearer {secret}",
                    "category": "rate_limited",
                },
                "metadata": {
                    "auth_plan": [
                        {
                            "auth_shape": "bearer",
                            "header_names": ["Authorization"],
                            "query_names": ["api-version"],
                            "leaked": secret,
                        }
                    ],
                    "candidate_attempts": [
                        {
                            "route": "responses",
                            "status": 429,
                            "auth_shape": "bearer",
                            "header_names": ["Authorization"],
                            "query_names": ["api-version"],
                            "error": {"message": f"api-key=azure-secret-value {secret}"},
                        }
                    ],
                },
            },
            stderr_lines=[
                {"event": "request_start", "auth_shape": "bearer", "header_names": ["Authorization"], "query_names": ["api-version"]},
                {"event": "request_finish", "status": 429, "error_code": "rate_limit_exceeded", "message": secret},
            ],
        )
        proc = run_cli(["job-status", "--job", str(job_dir), "--diagnose"], root)
        assert proc.returncode == 0, proc.stderr + proc.stdout
        assert secret not in proc.stdout
        assert "azure-secret-value" not in proc.stdout
        envelope = json.loads(proc.stdout)
        result = envelope["outputs"][0]["result"]
        assert result["outputs"][0]["headers"]["Authorization"] == "[REDACTED_SECRET]"
        assert result["outputs"][0]["headers"]["api-key"] == "[REDACTED_SECRET]"
        assert envelope["outputs"][0]["diagnosis"]["category"] == "rate_limited"


def test_stderr_only_diagnosis_reconstructs_request_finish():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        job_dir = write_job(
            root,
            job_status="failed",
            stdout_payload=None,
            stderr_lines=[
                {"event": "request_start", "route": "responses", "endpoint": "https://api.example/v1/responses", "auth_source": "env:OPENAI_API_KEY"},
                {"event": "request_finish", "route": "responses", "status": 429, "error_code": "rate_limit_exceeded", "request_id": "req-stderr", "latency_ms": 456, "base_url_source": "cli"},
            ],
            extra_metadata={"exit_code": 1},
        )
        proc = run_cli(["job-diagnose", "--job", str(job_dir), "--format", "json"], root)
        assert proc.returncode == 0, proc.stderr + proc.stdout
        diagnosis = json.loads(proc.stdout)["outputs"][0]["diagnosis"]
        assert diagnosis["category"] in {"child_no_result", "rate_limited"}
        assert any(item.get("request_id") == "req-stderr" for item in diagnosis["attempts"])
        assert any(item.get("error_code") == "rate_limit_exceeded" for item in diagnosis["evidence"])


def test_job_cancel_dry_run_does_not_modify_files():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        job_dir = write_job(root, job_status="running", extra_metadata={"pid": 111, "runner_pid": 111, "child_pid": 222})
        before_job = (job_dir / "job.json").read_text(encoding="utf-8")
        before_stdout = (job_dir / "stdout.json").read_text(encoding="utf-8")
        proc = run_cli(["job-cancel", "--job", str(job_dir), "--dry-run"], root)
        assert proc.returncode == 0, proc.stderr + proc.stdout
        envelope = json.loads(proc.stdout)
        assert envelope["status"] == "dry_run"
        assert {item["pid"] for item in envelope["outputs"][0]["cancel_plan"]} == {111, 222}
        assert (job_dir / "job.json").read_text(encoding="utf-8") == before_job
        assert (job_dir / "stdout.json").read_text(encoding="utf-8") == before_stdout


def test_job_cancel_completed_job_returns_already_final_without_stdout_change():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        job_dir = write_job(root, job_status="completed", stdout_payload={"ok": True, "status": "completed", "command": "henry.generate", "outputs": []})
        before_stdout = (job_dir / "stdout.json").read_text(encoding="utf-8")
        proc = run_cli(["job-cancel", "--job", str(job_dir)], root)
        assert proc.returncode == 0, proc.stderr + proc.stdout
        assert json.loads(proc.stdout)["status"] == "already_final"
        assert (job_dir / "stdout.json").read_text(encoding="utf-8") == before_stdout


def test_job_cancel_success_writes_cancelled_metadata_envelope_and_events():
    mod = load_module()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        job_dir = write_job(root, job_status="running", extra_metadata={"pid": 111, "runner_pid": 111, "child_pid": 222})
        out = io.StringIO()
        with patched(mod, "pid_running", lambda pid: int(pid) in {111, 222}):
            with patched(mod, "terminate_pid", lambda pid: {"pid": int(pid), "ok": True, "message": "terminated", "alive_after": False}):
                with contextlib.redirect_stdout(out):
                    code = mod.command_job_cancel(argparse.Namespace(job=str(job_dir), jobs_dir=None, reason="test cancel", dry_run=False, format="json"))
        assert code == 0
        envelope = json.loads(out.getvalue())
        assert envelope["status"] == "cancelled"
        metadata = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
        assert metadata["status"] == "cancelled"
        assert metadata["cancel_reason"] == "test cancel"
        stdout_payload = json.loads((job_dir / "stdout.json").read_text(encoding="utf-8"))
        assert stdout_payload["status"] == "job_cancelled"
        stderr_text = (job_dir / "stderr.jsonl").read_text(encoding="utf-8")
        assert "job_cancel_requested" in stderr_text
        assert "job_cancel_finish" in stderr_text


def test_job_cancel_failure_reports_cancel_failed_without_completed_status():
    mod = load_module()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        job_dir = write_job(root, job_status="running", extra_metadata={"pid": 333, "runner_pid": 333, "child_pid": 444})
        out = io.StringIO()
        with patched(mod, "pid_running", lambda pid: int(pid) in {333, 444}):
            with patched(mod, "terminate_pid", lambda pid: {"pid": int(pid), "ok": False, "message": "denied", "alive_after": True}):
                with contextlib.redirect_stdout(out):
                    code = mod.command_job_cancel(argparse.Namespace(job=str(job_dir), jobs_dir=None, reason=None, dry_run=False, format="json"))
        assert code != 0
        envelope = json.loads(out.getvalue())
        assert envelope["status"] == "cancel_failed"
        metadata = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
        assert metadata["status"] != "completed"


def test_job_runner_preserves_cancelled_status_and_stdout():
    mod = load_module()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        job_dir = write_job(root, job_status="cancelled", extra_metadata={"cancel_attempts": [{"pid": 1, "ok": True}], "cancel_reason": "already cancelled"})
        stdout_payload = {
            "ok": False,
            "status": "job_cancelled",
            "command": "henry.generate",
            "provider": {"type": "henry-local-background-job"},
            "outputs": [],
            "error": {"code": "job_cancelled", "message": "Background job was cancelled."},
            "metadata": {},
        }
        (job_dir / "stdout.json").write_text(json.dumps(stdout_payload), encoding="utf-8")
        before_stdout = (job_dir / "stdout.json").read_text(encoding="utf-8")
        child_tmp = job_dir / "stdout.json.fake.child.tmp"
        child_tmp.write_text("", encoding="utf-8")
        with patched(mod.uuid, "uuid4", lambda: type("FakeUuid", (), {"hex": "fake"})()):
            code = mod.command_job_runner(argparse.Namespace(job_path=str(job_dir / "job.json")))
        assert code == 1
        metadata = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
        assert metadata["status"] == "cancelled"
        assert (job_dir / "stdout.json").read_text(encoding="utf-8") == before_stdout


def test_job_status_preserves_cancel_failed_without_child_no_result_overwrite():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        job_dir = write_job(
            root,
            job_status="cancel_failed",
            stdout_payload=None,
            extra_metadata={
                "cancel_attempts": [{"pid": 333, "ok": False, "message": "denied", "alive_after": True}],
                "cancel_failed_at": "2026-06-08T00:01:00+00:00",
            },
        )
        proc = run_cli(["job-status", "--job", str(job_dir), "--diagnose"], root)
        assert proc.returncode == 0, proc.stderr + proc.stdout
        envelope = json.loads(proc.stdout)
        assert envelope["status"] == "cancel_failed"
        assert envelope["outputs"][0]["diagnosis"]["category"] == "cancel_failed"
        assert (job_dir / "stdout.json").read_text(encoding="utf-8") == ""


if __name__ == "__main__":
    tests = [
        test_job_diagnose_json_summarizes_failed_job_and_redacts,
        test_job_diagnose_human_contains_actionable_sections_and_redacts,
        test_job_status_diagnose_keeps_default_compatible_and_adds_diagnosis_when_requested,
        test_job_status_diagnose_redacts_nested_result_outputs,
        test_stderr_only_diagnosis_reconstructs_request_finish,
        test_job_cancel_dry_run_does_not_modify_files,
        test_job_cancel_completed_job_returns_already_final_without_stdout_change,
        test_job_cancel_success_writes_cancelled_metadata_envelope_and_events,
        test_job_cancel_failure_reports_cancel_failed_without_completed_status,
        test_job_runner_preserves_cancelled_status_and_stdout,
        test_job_status_preserves_cancel_failed_without_child_no_result_overwrite,
    ]
    for test in tests:
        test()
    print(f"{len(tests)} p1.5 diagnostics/cancel tests passed")
