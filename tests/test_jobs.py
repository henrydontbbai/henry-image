from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from helpers import load_module, patched, run_cli


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


@pytest.mark.parametrize(
    ("child_result", "command"),
    [
        ([], ["job-status"]),
        ({"status": []}, ["job-status"]),
        ({"status": "failed", "error": []}, ["job-diagnose", "--format", "json"]),
        ([], ["job-cancel"]),
        ([], ["job-cleanup", "--older-than", "1d"]),
    ],
)
def test_job_commands_handle_invalid_child_result_without_traceback(child_result, command):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        jobs_dir = root / "jobs"
        job_dir = write_job(jobs_dir, stdout_payload=child_result)
        if command[0] == "job-cleanup":
            args = [*command, "--jobs-dir", str(jobs_dir)]
        else:
            args = [*command, "--job", str(job_dir)]

        proc = run_cli(args, root)

        assert "Traceback" not in proc.stderr
        assert proc.returncode == 0
        payload = json.loads(proc.stdout)
        if command[0] in {"job-status", "job-diagnose"}:
            assert payload["status"] == "child_invalid_json"


def test_pid_running_on_windows_does_not_send_a_console_signal():
    if os.name != "nt":
        pytest.skip("Windows-specific process probe regression")

    module = load_module()

    def fail_if_signalled(_pid, _signal):
        raise AssertionError("Windows liveness checks must not call os.kill")

    with patched(module.os, "kill", fail_if_signalled):
        assert module.pid_running(os.getpid()) is True


def test_pid_running_treats_linux_zombie_as_exited():
    module = load_module()

    def fail_if_probed(_pid, _signal):
        raise AssertionError("Linux zombie detection should not fall through to os.kill")

    with patched(module.sys, "platform", "linux"):
        with patched(module, "linux_process_state", lambda _pid: "Z"):
            with patched(module.os, "kill", fail_if_probed):
                assert module.pid_running(123) is False


def test_process_identity_is_available_on_supported_platforms():
    if os.name != "nt" and not sys.platform.startswith("linux"):
        pytest.skip("Process identities are supported on Windows and Linux")

    module = load_module()
    identity = module.process_identity(os.getpid())

    assert identity["scheme"] in {"windows_filetime", "linux_proc_starttime"}
    assert identity["value"]


def test_job_state_requires_matching_process_identity():
    module = load_module()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        expected = {"scheme": "test", "value": "original"}
        job_dir = write_job(
            root,
            job_status="running",
            extra_metadata={"pid": 123, "process_identity": expected},
        )
        metadata = module.read_job_metadata(job_dir)

        with patched(module, "pid_running", lambda _pid: True):
            with patched(module, "process_identity", lambda _pid: {"scheme": "test", "value": "reused"}):
                state, result = module.infer_job_state(job_dir, metadata)

    assert state == "child_no_result"
    assert result is None


def test_legacy_job_without_identity_can_still_report_running():
    module = load_module()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        job_dir = write_job(root, job_status="running", extra_metadata={"pid": 123})
        metadata = module.read_job_metadata(job_dir)

        with patched(module, "pid_running", lambda _pid: True):
            state, result = module.infer_job_state(job_dir, metadata)

    assert state == "running"
    assert result is None


def test_matching_job_identity_reports_running():
    module = load_module()
    expected = {"scheme": "test", "value": "original"}

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        job_dir = write_job(
            root,
            job_status="running",
            extra_metadata={"pid": 123, "process_identity": expected},
        )
        metadata = module.read_job_metadata(job_dir)

        with patched(module, "pid_running", lambda _pid: True):
            with patched(module, "process_identity", lambda _pid: dict(expected)):
                state, result = module.infer_job_state(job_dir, metadata)

    assert state == "running"
    assert result is None


def test_cancel_pending_job_converges_to_cancelled_after_process_exit():
    module = load_module()
    expected = {"scheme": "test", "value": "original"}

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        job_dir = write_job(
            root,
            job_status="cancel_pending",
            extra_metadata={"pid": 123, "process_identity": expected},
        )
        metadata = module.read_job_metadata(job_dir)

        with patched(module, "pid_running", lambda _pid: False):
            state, result = module.infer_job_state(job_dir, metadata)

        persisted = module.read_job_metadata(job_dir)

    assert state == "cancelled"
    assert result is None
    assert persisted["status"] == "cancelled"


def test_cancel_pending_convergence_survives_metadata_write_failure():
    module = load_module()
    expected = {"scheme": "test", "value": "original"}

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        job_dir = write_job(
            root,
            job_status="cancel_pending",
            extra_metadata={"pid": 123, "process_identity": expected},
        )
        metadata = module.read_job_metadata(job_dir)

        with patched(module, "pid_running", lambda _pid: False):
            with patched(
                module,
                "write_job_metadata",
                lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("replace failed")),
            ):
                state, result = module.infer_job_state(job_dir, metadata)

    assert state == "cancelled"
    assert result is None


def test_cancelled_job_without_child_result_stays_cancelled():
    module = load_module()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        job_dir = write_job(root, job_status="cancelled", extra_metadata={"pid": 0})
        metadata = module.read_job_metadata(job_dir)

        state, result = module.infer_job_state(job_dir, metadata)

    assert state == "cancelled"
    assert result is None


def test_cancel_failed_job_status_stays_visible_while_process_runs():
    module = load_module()
    expected = {"scheme": "test", "value": "original"}

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        job_dir = write_job(
            root,
            job_status="cancel_failed",
            extra_metadata={"pid": 123, "process_identity": expected},
        )
        metadata = module.read_job_metadata(job_dir)

        with patched(module, "pid_running", lambda _pid: True):
            with patched(module, "process_identity", lambda _pid: dict(expected)):
                state, result = module.infer_job_state(job_dir, metadata)

    assert state == "cancel_failed"
    assert result is None


def test_new_background_job_writes_process_identity():
    module = load_module()
    stdout = io.StringIO()
    identity = {"scheme": "test", "value": "created"}

    class FakeProcess:
        pid = 456

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        args = argparse.Namespace(
            jobs_dir=str(root),
            route="images",
            out=str(root / "result.png"),
        )

        with patched(module, "build_job_id", lambda: "job-created"):
            with patched(module.subprocess, "Popen", lambda *_args, **_kwargs: FakeProcess()):
                with patched(module, "process_identity", lambda _pid: dict(identity)):
                    with contextlib.redirect_stdout(stdout):
                        code = module.start_background_job("generate", args)

        metadata = module.read_job_metadata(root / "job-created")

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert payload["status"] == "started"
    assert metadata["process_identity"] == identity


def test_background_job_fails_when_process_identity_cannot_be_captured():
    module = load_module()
    if os.name != "nt" and not sys.platform.startswith("linux"):
        pytest.skip("New background jobs require identity capture on Windows and Linux")
    stdout = io.StringIO()
    terminated = []

    class FakeProcess:
        pid = 456

        def terminate(self):
            terminated.append("terminate")

        def wait(self, timeout):
            assert timeout == 2
            terminated.append("wait")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        args = argparse.Namespace(
            jobs_dir=str(root),
            route="images",
            out=str(root / "result.png"),
        )

        with patched(module, "build_job_id", lambda: "job-created"):
            with patched(module.subprocess, "Popen", lambda *_args, **_kwargs: FakeProcess()):
                with patched(module, "process_identity", lambda _pid: None):
                    with contextlib.redirect_stdout(stdout):
                        code = module.start_background_job("generate", args)

        assert not (root / "job-created").exists()

    payload = json.loads(stdout.getvalue())
    assert code == 1
    assert payload["status"] == "job_start_failed"
    assert payload["error"]["code"] == "job_start_failed"
    assert terminated == ["terminate", "wait"]


def test_background_job_terminates_child_when_metadata_write_fails():
    module = load_module()
    stdout = io.StringIO()
    terminated = []

    class FakeProcess:
        pid = 456

        def terminate(self):
            terminated.append("terminate")

        def wait(self, timeout):
            assert timeout == 2
            terminated.append("wait")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        args = argparse.Namespace(
            jobs_dir=str(root),
            route="images",
            out=str(root / "result.png"),
        )

        with patched(module, "build_job_id", lambda: "job-created"):
            with patched(module.subprocess, "Popen", lambda *_args, **_kwargs: FakeProcess()):
                with patched(module, "process_identity", lambda _pid: {"scheme": "test", "value": "created"}):
                    with patched(
                        module,
                        "write_job_metadata",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("replace failed")),
                    ):
                        with contextlib.redirect_stdout(stdout):
                            code = module.start_background_job("generate", args)

        job_dir = root / "job-created"
        assert not job_dir.exists()

    payload = json.loads(stdout.getvalue())
    assert code == 1
    assert payload["status"] == "job_start_failed"
    assert payload["error"]["code"] == "job_start_failed"
    assert terminated == ["terminate", "wait"]


@pytest.mark.parametrize("setup", ["jobs_path_is_file", "job_dir_is_file"])
def test_background_job_returns_structured_error_when_job_directory_creation_fails(setup):
    module = load_module()
    stdout = io.StringIO()
    started = []

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        jobs_dir = root / "jobs"
        if setup == "jobs_path_is_file":
            jobs_dir.write_text("not a directory", encoding="utf-8")
        else:
            jobs_dir.mkdir()
            (jobs_dir / "job-created").write_text("not a directory", encoding="utf-8")
        args = argparse.Namespace(
            jobs_dir=str(jobs_dir),
            route="images",
            out=str(root / "result.png"),
        )

        with patched(module, "build_job_id", lambda: "job-created"):
            with patched(
                module.subprocess,
                "Popen",
                lambda *_args, **_kwargs: started.append("started"),
            ):
                with contextlib.redirect_stdout(stdout):
                    code = module.start_background_job("generate", args)

    payload = json.loads(stdout.getvalue())
    assert code == 1
    assert payload["status"] == "job_start_failed"
    assert payload["error"]["code"] == "job_start_failed"
    assert payload["error"]["category"] == "job_start_failed"
    assert started == []


def test_background_job_force_kills_child_when_terminate_times_out():
    module = load_module()
    stdout = io.StringIO()
    actions = []

    class FakeProcess:
        pid = 456

        def terminate(self):
            actions.append("terminate")

        def kill(self):
            actions.append("kill")

        def wait(self, timeout):
            actions.append("wait")
            if actions.count("wait") == 1:
                raise subprocess.TimeoutExpired(cmd="child", timeout=timeout)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        args = argparse.Namespace(
            jobs_dir=str(root),
            route="images",
            out=str(root / "result.png"),
        )

        with patched(module, "build_job_id", lambda: "job-created"):
            with patched(module.subprocess, "Popen", lambda *_args, **_kwargs: FakeProcess()):
                with patched(module, "process_identity", lambda _pid: {"scheme": "test", "value": "created"}):
                    with patched(
                        module,
                        "write_job_metadata",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("replace failed")),
                    ):
                        with contextlib.redirect_stdout(stdout):
                            code = module.start_background_job("generate", args)

    payload = json.loads(stdout.getvalue())
    assert code == 1
    assert payload["status"] == "job_start_failed"
    assert actions == ["terminate", "wait", "kill", "wait"]


def test_verified_termination_stops_owned_child_process():
    module = load_module()
    if os.name != "nt" and not sys.platform.startswith("linux"):
        pytest.skip("Verified process termination is supported on Windows and Linux")

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        creationflags=creationflags,
    )
    try:
        identity = module.process_identity(process.pid)
        assert identity is not None

        module.send_verified_termination(process.pid, identity)

        assert module.wait_for_process_exit(process.pid, identity, timeout=2.0) is True
        process.wait(timeout=2.0)
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=2.0)


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


def test_legacy_job_cancel_refuses_unverified_identity_without_signalling():
    module = load_module()
    stdout = io.StringIO()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        job_dir = write_job(root, job_status="running", extra_metadata={"pid": 123})
        args = argparse.Namespace(job=str(job_dir), jobs_dir=None, dry_run=False)

        with patched(module, "infer_job_state", lambda *_args: ("running", None)):
            with patched(module, "send_verified_termination", lambda *_args: (_ for _ in ()).throw(AssertionError("must not signal"))):
                with contextlib.redirect_stdout(stdout):
                    code = module.command_job_cancel(args)

    payload = json.loads(stdout.getvalue())
    assert code == 1
    assert payload["status"] == "identity_unverified"
    assert payload["error"]["category"] == "identity_unverified"


@pytest.mark.parametrize(
    ("wait_result", "expected_status"),
    [
        (True, "cancelled"),
        (False, "cancel_pending"),
    ],
)
def test_job_cancel_reports_verified_termination_result(wait_result, expected_status):
    module = load_module()
    stdout = io.StringIO()
    identity = {"scheme": "test", "value": "original"}

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        job_dir = write_job(
            root,
            job_status="running",
            extra_metadata={"pid": 123, "process_identity": identity},
        )
        args = argparse.Namespace(job=str(job_dir), jobs_dir=None, dry_run=False)
        sent = []

        with patched(module, "infer_job_state", lambda *_args: ("running", None)):
            with patched(module, "send_verified_termination", lambda pid, expected: sent.append((pid, expected))):
                with patched(module, "wait_for_process_exit", lambda *_args, **_kwargs: wait_result):
                    with contextlib.redirect_stdout(stdout):
                        code = module.command_job_cancel(args)

        metadata = module.read_job_metadata(job_dir)

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert payload["status"] == expected_status
    assert metadata["status"] == expected_status
    assert sent == [(123, identity)]


def test_job_cancel_reports_signal_failure():
    module = load_module()
    stdout = io.StringIO()
    identity = {"scheme": "test", "value": "original"}

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        job_dir = write_job(
            root,
            job_status="running",
            extra_metadata={"pid": 123, "process_identity": identity},
        )
        args = argparse.Namespace(job=str(job_dir), jobs_dir=None, dry_run=False)

        with patched(module, "infer_job_state", lambda *_args: ("running", None)):
            with patched(module, "send_verified_termination", lambda *_args: (_ for _ in ()).throw(OSError("denied"))):
                with contextlib.redirect_stdout(stdout):
                    code = module.command_job_cancel(args)

        metadata = module.read_job_metadata(job_dir)

    payload = json.loads(stdout.getvalue())
    assert code == 1
    assert payload["status"] == "cancel_failed"
    assert payload["error"]["category"] == "cancel_failed"
    assert metadata["status"] == "cancel_failed"


@pytest.mark.parametrize("signal_fails", [False, True])
def test_job_cancel_returns_structured_failure_when_status_write_fails(signal_fails):
    module = load_module()
    stdout = io.StringIO()
    identity = {"scheme": "test", "value": "original"}

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        job_dir = write_job(
            root,
            job_status="running",
            extra_metadata={"pid": 123, "process_identity": identity},
        )
        args = argparse.Namespace(job=str(job_dir), jobs_dir=None, dry_run=False)

        def send_termination(*_args):
            if signal_fails:
                raise OSError("signal denied")

        with patched(module, "infer_job_state", lambda *_args: ("running", None)):
            with patched(module, "send_verified_termination", send_termination):
                with patched(module, "wait_for_process_exit", lambda *_args, **_kwargs: True):
                    with patched(
                        module,
                        "write_job_metadata",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("replace failed")),
                    ):
                        with contextlib.redirect_stdout(stdout):
                            code = module.command_job_cancel(args)

    payload = json.loads(stdout.getvalue())
    assert code == 1
    assert payload["status"] == "cancel_failed"
    assert payload["error"]["code"] == "cancel_failed"
    assert "replace failed" in payload["error"]["message"]


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


def test_job_cleanup_preserves_an_old_job_while_its_process_is_running():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        jobs_dir = root / "jobs"
        active = write_job(
            jobs_dir,
            job_id="active-old-job",
            job_status="running",
            extra_metadata={
                "pid": os.getpid(),
                "created_at": "2020-01-01T00:00:00+00:00",
            },
        )

        cleanup = run_cli(["job-cleanup", "--jobs-dir", str(jobs_dir), "--older-than", "1d"], root)

        assert cleanup.returncode == 0, cleanup.stderr + cleanup.stdout
        removed = json.loads(cleanup.stdout)["outputs"][0]["removed"]
        assert all(item["job_id"] != "active-old-job" for item in removed)
        assert active.exists()


def test_job_cleanup_preserves_cancel_pending_job():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        jobs_dir = root / "jobs"
        pending = write_job(
            jobs_dir,
            job_id="pending-old-job",
            job_status="cancel_pending",
            extra_metadata={
                "pid": 0,
                "created_at": "2020-01-01T00:00:00+00:00",
            },
        )

        cleanup = run_cli(["job-cleanup", "--jobs-dir", str(jobs_dir), "--older-than", "1d"], root)

        assert cleanup.returncode == 0, cleanup.stderr + cleanup.stdout
        removed = json.loads(cleanup.stdout)["outputs"][0]["removed"]
        assert all(item["job_id"] != "pending-old-job" for item in removed)
        assert pending.exists()


def test_job_cleanup_removes_cancel_pending_job_after_process_exit():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        jobs_dir = root / "jobs"
        finished = write_job(
            jobs_dir,
            job_id="finished-cancel-job",
            job_status="cancel_pending",
            extra_metadata={
                "pid": 0,
                "process_identity": {"scheme": "test", "value": "original"},
                "created_at": "2020-01-01T00:00:00+00:00",
            },
        )

        cleanup = run_cli(["job-cleanup", "--jobs-dir", str(jobs_dir), "--older-than", "1d"], root)

        assert cleanup.returncode == 0, cleanup.stderr + cleanup.stdout
        removed = json.loads(cleanup.stdout)["outputs"][0]["removed"]
        assert any(item["job_id"] == "finished-cancel-job" for item in removed)
        assert not finished.exists()


def test_job_cleanup_preserves_cancel_failed_job_while_process_runs():
    module = load_module()
    stdout = io.StringIO()
    expected = {"scheme": "test", "value": "original"}

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        job_dir = write_job(
            root,
            job_id="failed-cancel-job",
            job_status="cancel_failed",
            extra_metadata={
                "pid": 123,
                "process_identity": expected,
                "created_at": "2020-01-01T00:00:00+00:00",
            },
        )
        args = argparse.Namespace(jobs_dir=str(root), older_than="1d")

        with patched(module, "pid_running", lambda _pid: True):
            with patched(module, "process_identity", lambda _pid: dict(expected)):
                with contextlib.redirect_stdout(stdout):
                    code = module.command_job_cleanup(args)
        assert job_dir.exists()

    payload = json.loads(stdout.getvalue())
    assert code == 0
    assert payload["outputs"][0]["removed"] == []


def test_job_metadata_write_is_atomic_when_replace_fails():
    module = load_module()

    with tempfile.TemporaryDirectory() as tmp:
        job_dir = Path(tmp)
        job_file = job_dir / "job.json"
        job_file.write_text('{"status":"old"}', encoding="utf-8")

        with patched(
            module.os,
            "replace",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("replace failed")),
        ):
            try:
                module.write_job_metadata(job_dir, {"status": "new"})
            except OSError as exc:
                assert "replace failed" in str(exc)
            else:
                raise AssertionError("Expected metadata replace failure")

        assert json.loads(job_file.read_text(encoding="utf-8"))["status"] == "old"
        assert not list(job_dir.glob("*.tmp-*"))


def test_job_commands_return_structured_error_for_invalid_metadata():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        job_dir = root / "broken-job"
        job_dir.mkdir()
        (job_dir / "job.json").write_text("{bad", encoding="utf-8")

        for args in (
            ["job-status", "--job", str(job_dir)],
            ["job-list", "--jobs-dir", str(root)],
            ["job-cleanup", "--jobs-dir", str(root), "--older-than", "1d"],
        ):
            proc = run_cli(args, root)
            assert "Traceback" not in proc.stderr
            payload = json.loads(proc.stdout)
            assert proc.returncode == 1
            assert payload["status"] == "invalid_job_metadata"
            assert payload["error"]["code"] == "invalid_job_metadata"


@pytest.mark.parametrize(
    "metadata",
    [
        {},
        {"job_id": "partial"},
        {"job_id": "partial", "status": "running", "pid": 0},
    ],
)
def test_job_commands_reject_missing_required_metadata_fields(metadata):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        job_dir = root / "broken-job"
        job_dir.mkdir()
        (job_dir / "job.json").write_text(json.dumps(metadata), encoding="utf-8")

        proc = run_cli(["job-status", "--job", str(job_dir)], root)

        assert "Traceback" not in proc.stderr
        assert proc.returncode == 1
        payload = json.loads(proc.stdout)
        assert payload["status"] == "invalid_job_metadata"


@pytest.mark.parametrize(
    "metadata",
    [
        {"pid": {"unexpected": "object"}},
        {"pid": 1 << 80},
        {"created_at": ["2020-01-01T00:00:00+00:00"]},
    ],
)
def test_job_commands_return_structured_error_for_invalid_metadata_fields(metadata):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        job_dir = root / "broken-job"
        job_dir.mkdir()
        (job_dir / "job.json").write_text(json.dumps(metadata), encoding="utf-8")

        for args in (
            ["job-status", "--job", str(job_dir)],
            ["job-list", "--jobs-dir", str(root)],
            ["job-cleanup", "--jobs-dir", str(root), "--older-than", "1d"],
        ):
            proc = run_cli(args, root)
            assert "Traceback" not in proc.stderr
            payload = json.loads(proc.stdout)
            assert proc.returncode == 1
            assert payload["status"] == "invalid_job_metadata"
            assert payload["error"]["code"] == "invalid_job_metadata"


def test_job_cleanup_does_not_report_failed_deletion_as_removed():
    module = load_module()
    stdout = io.StringIO()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        job_dir = write_job(
            root,
            job_id="undeletable-job",
            extra_metadata={"created_at": "2020-01-01T00:00:00+00:00"},
        )
        args = argparse.Namespace(jobs_dir=str(root), older_than="1d")

        with patched(
            module.shutil,
            "rmtree",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(PermissionError("denied")),
        ):
            with contextlib.redirect_stdout(stdout):
                code = module.command_job_cleanup(args)

        payload = json.loads(stdout.getvalue())
        result = payload["outputs"][0]
        assert code == 1
        assert payload["status"] == "cleanup_failed"
        assert result["removed"] == []
        assert result["failed"][0]["job_id"] == "undeletable-job"
        assert job_dir.exists()
