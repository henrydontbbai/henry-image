import argparse
import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "henry_image.py"


def load_module():
    spec = importlib.util.spec_from_file_location("henry_image_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_cli(args, cwd):
    env = os.environ.copy()
    env["HENRY_IMAGE_DISABLE_WINDOWS_USER_ENV"] = "1"
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd, env=env, text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=30)


@contextlib.contextmanager
def patched(obj, name, value):
    old = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield
    finally:
        setattr(obj, name, old)


def test_candidate_policy_filters_base_url_candidates():
    mod = load_module()
    candidates = [
        ("https://cli.example/v1", "cli"),
        ("https://env.example/v1", "ENV_BASE_URL"),
        ("https://default.example/v1", "default"),
    ]
    with patched(mod, "windows_user_env", lambda _name: None):
        with patched(mod, "dedicated_base_url_candidate", lambda: None):
            with patched(mod, "base_url_candidates", lambda base_url=None: candidates):
                with patched(mod, "image_model_base_url_candidates", lambda _args: []):
                    with patched(mod, "active_image_model_base_url_candidates", lambda _args: []):
                        explicit = argparse.Namespace(base_url="https://cli.example/v1", route="auto", candidate_policy="auto")
                        assert mod.policy_base_url_candidates(explicit) == candidates[:1]

                    strict = argparse.Namespace(base_url=None, route="auto", candidate_policy="strict")
                    assert mod.policy_base_url_candidates(strict) == candidates[:1]

                    wide = argparse.Namespace(base_url=None, route="auto", candidate_policy="all")
                    assert mod.policy_base_url_candidates(wide) == candidates

                    explicit_route = argparse.Namespace(base_url=None, route="responses", candidate_policy="auto")
                    assert mod.policy_base_url_candidates(explicit_route) == candidates[:1]


def test_dedicated_henry_image_base_url_wins_over_codex_candidates():
    mod = load_module()
    with tempfile.TemporaryDirectory() as tmp_config_dir:
        root = Path(tmp_config_dir)
        config_path = root / "config.toml"
        config_path.write_text(
            "\n".join(
                (
                    'model_provider = "router"',
                    'model = "gpt-image-2"',
                    "",
                    "[model_providers.router]",
                    'base_url = "http://127.0.0.1:25817/codex/router/v1"',
                    "requires_openai_auth = false",
                    "",
                    "[model_providers.image_direct]",
                    'base_url = "http://127.0.0.1:25817/codex/by-provider/image_direct/v1"',
                    "requires_openai_auth = false",
                    "",
                    "[profiles.image_direct]",
                    'model_provider = "image_direct"',
                    'model = "gpt-image-2"',
                )
            ),
            encoding="utf-8",
        )
        env_updates = {
            "HENRY_IMAGE_CODEX_CONFIG": str(config_path),
            "HENRY_IMAGE_BASE_URL": "https://images.example/v1",
            "HENRY_IMAGE_API_KEY": "sk-dedicated-henry-image",
            "HENRY_IMAGE_MODEL": "custom-response-image",
            "HENRY_IMAGE_IMAGE_MODEL": "custom-image-model",
        }
        old_env = {key: os.environ.get(key) for key in env_updates}
        try:
            os.environ.update(env_updates)
            args = argparse.Namespace(
                base_url=None,
                route="responses",
                candidate_policy="auto",
                model="gpt-5",
                image_model="gpt-image-2",
            )
            mod.apply_model_env_defaults(args)
            assert args.model == "custom-response-image"
            assert args.image_model == "custom-image-model"
            assert mod.base_url_candidates(None)[0] == ("https://images.example/v1", "HENRY_IMAGE_BASE_URL")
            assert mod.policy_base_url_candidates(args) == [("https://images.example/v1", "HENRY_IMAGE_BASE_URL")]
            assert mod.image_model_base_url_candidates(args) == []
            assert mod.auth_candidates(args.api_key_env if hasattr(args, "api_key_env") else None, "HENRY_IMAGE_BASE_URL")[0][1] == "HENRY_IMAGE_API_KEY"
        finally:
            for key, value in old_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


def test_windows_user_env_fallback_when_process_env_missing():
    mod = load_module()
    registry_values = {
        "HENRY_IMAGE_BASE_URL": "https://registry-images.example/v1",
        "HENRY_IMAGE_API_KEY": "sk-registry-henry-image",
        "HENRY_IMAGE_MODEL": "registry-response-model",
        "HENRY_IMAGE_IMAGE_MODEL": "registry-image-model",
    }
    old_env = {key: os.environ.get(key) for key in registry_values}
    try:
        for key in registry_values:
            os.environ.pop(key, None)
        with patched(mod, "windows_user_env", lambda name: registry_values.get(name)):
            args = argparse.Namespace(
                base_url=None,
                route="responses",
                candidate_policy="auto",
                model="gpt-5",
                image_model="gpt-image-2",
            )
            mod.apply_model_env_defaults(args)
            assert args.model == "registry-response-model"
            assert args.image_model == "registry-image-model"
            assert mod.base_url_candidates(None)[0] == ("https://registry-images.example/v1", "HENRY_IMAGE_BASE_URL")
            assert mod.policy_base_url_candidates(args) == [("https://registry-images.example/v1", "HENRY_IMAGE_BASE_URL")]
            assert mod.api_key_candidates(None)[0][1] == "HENRY_IMAGE_API_KEY"
    finally:
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_request_finish_and_failure_taxonomy_are_reported():
    mod = load_module()
    args = argparse.Namespace(
        api_key_env=None,
        background="auto",
        base_url="https://api.example/v1",
        base_url_source="cli",
        candidate_policy="auto",
        dry_run=False,
        image_model="gpt-image-2",
        images_compat="auto",
        images_response_format="auto",
        input_fidelity="auto",
        model="gpt-5",
        moderation="auto",
        n=1,
        output_compression=None,
        output_format="png",
        partial_images=0,
        quality="medium",
        retries=0,
        route="responses",
        size="1024x1024",
        timeout=1,
    )
    fake_result = mod.ApiResult(
        False,
        429,
        None,
        {"status": 429, "code": "rate_limit_exceeded", "message": "rate limit"},
        "req-test",
        123,
    )
    stderr = io.StringIO()
    with patched(mod, "auth_candidates", lambda *_args, **_kwargs: [("test-key", "test-auth")]):
        with patched(mod, "request_json", lambda *_args, **_kwargs: fake_result):
            with contextlib.redirect_stderr(stderr):
                result = mod.run_route_request(
                    route="responses",
                    command="henry.generate",
                    args=args,
                    payload={"input": "x", "tools": []},
                    prompt="x",
                    out="out.png",
                )
    events = [json.loads(line) for line in stderr.getvalue().splitlines()]
    assert result["status"] == "rate_limited"
    assert result["error"]["category"] == "rate_limited"
    finish = [event for event in events if event["event"] == "request_finish"]
    assert finish and finish[0]["status"] == 429
    assert finish[0]["error_code"] == "rate_limit_exceeded"
    assert finish[0]["latency_ms"] == 123


def test_route_auto_does_not_fallback_for_blocked_failure_categories():
    mod = load_module()
    blocked_errors = [
        {"status": 400, "code": "safety_violation", "message": "safety policy", "category": "content_policy"},
        {"status": 429, "code": "insufficient_quota", "message": "quota exhausted", "category": "quota_exceeded"},
        {"status": 429, "code": "rate_limit_exceeded", "message": "rate limit", "category": "rate_limited"},
        {"status": 400, "code": "invalid_request_error", "message": "bad parameter", "category": "bad_parameter"},
    ]
    for error_obj in blocked_errors:
        routes = []

        def fake_run_route_request(*, route, command, args, payload, prompt, out, extra_metadata=None):
            routes.append(route)
            return mod.envelope(
                ok=False,
                command=command,
                status=error_obj["category"],
                provider={"type": "fake"},
                error_obj=error_obj,
                metadata={"route": route},
            )

        args = argparse.Namespace(route="auto", base_url=None, candidate_policy="auto")
        with patched(mod, "policy_base_url_candidates", lambda _args: [("https://api.example/v1", "fake")]):
            with patched(mod, "run_route_request", fake_run_route_request):
                result = mod.run_request(command="henry.generate", args=args, payload={}, prompt="x", out="out.png")
        assert routes == ["responses"], error_obj
        assert result["status"] == error_obj["category"]


def test_batch_resume_skip_existing_result_jsonl_and_max_images():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        batch = root / "batch.jsonl"
        existing = root / "existing.png"
        existing.write_bytes(b"already")
        batch.write_text(
            "\n".join(
                [
                    json.dumps({"prompt": "already done", "out": str(root / "done.png")}),
                    json.dumps({"prompt": "existing output", "out": str(existing)}),
                    json.dumps({"prompt": "new dry run", "out": str(root / "new.png")}),
                ]
            ),
            encoding="utf-8",
        )
        result_jsonl = root / "results.jsonl"
        result_jsonl.write_text(
            json.dumps({"task_index": 1, "ok": True, "status": "completed", "out": str(root / "done.png")}) + "\n",
            encoding="utf-8",
        )
        proc = run_cli(
            [
                "batch",
                "--dry-run",
                "--input",
                str(batch),
                "--result-jsonl",
                str(result_jsonl),
                "--resume",
                "--skip-existing",
                "--max-images",
                "5",
                "--force",
            ],
            root,
        )
        assert proc.returncode == 0, proc.stderr + proc.stdout
        envelope = json.loads(proc.stdout)
        results = envelope["outputs"][0]["results"]
        statuses = [item["status"] for item in results]
        assert statuses == ["skipped", "skipped", "dry_run"]
        assert result_jsonl.exists()
        rows = [json.loads(line) for line in result_jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert len(rows) >= 3

        too_many = run_cli(
            ["batch", "--dry-run", "--input", str(batch), "--max-images", "2", "--force"],
            root,
        )
        assert too_many.returncode == 0, too_many.stderr + too_many.stdout
        assert json.loads(too_many.stdout)["status"] == "dry_run"

        blocked = run_cli(
            ["batch", "--input", str(batch), "--max-images", "2", "--force", "--base-url", "https://invalid.example/v1"],
            root,
        )
        assert blocked.returncode != 0
        blocked_envelope = json.loads(blocked.stdout)
        assert blocked_envelope["status"] == "validation_error"
        assert blocked_envelope["error"]["code"] == "max_images_exceeded"


def test_job_list_cleanup_and_watch():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        jobs_dir = root / "jobs"
        old = jobs_dir / "old-job"
        new = jobs_dir / "new-job"
        old.mkdir(parents=True)
        new.mkdir(parents=True)
        for path, job_id in ((old, "old-job"), (new, "new-job")):
            (path / "stdout.json").write_text(json.dumps({"ok": True, "status": "dry_run"}), encoding="utf-8")
            (path / "stderr.jsonl").write_text("", encoding="utf-8")
            (path / "job.json").write_text(
                json.dumps(
                    {
                        "job_id": job_id,
                        "status": "completed",
                        "pid": 0,
                        "created_at": "2020-01-01T00:00:00+00:00" if job_id == "old-job" else "2999-01-01T00:00:00+00:00",
                        "job_path": str(path),
                        "stdout": str(path / "stdout.json"),
                        "stderr": str(path / "stderr.jsonl"),
                    }
                ),
                encoding="utf-8",
            )

        listed = run_cli(["job-list", "--jobs-dir", str(jobs_dir)], root)
        assert listed.returncode == 0, listed.stderr + listed.stdout
        jobs = json.loads(listed.stdout)["outputs"][0]["jobs"]
        assert {job["job_id"] for job in jobs} == {"old-job", "new-job"}

        watched = run_cli(["job-status", "--job", str(new), "--watch", "--interval", "0.01"], root)
        assert watched.returncode == 0, watched.stderr + watched.stdout
        assert json.loads(watched.stdout)["status"] == "completed"

        cleanup = run_cli(["job-cleanup", "--jobs-dir", str(jobs_dir), "--older-than", "365d"], root)
        assert cleanup.returncode == 0, cleanup.stderr + cleanup.stdout
        removed = json.loads(cleanup.stdout)["outputs"][0]["removed"]
        assert any(item["job_id"] == "old-job" for item in removed)
        assert not old.exists()
        assert new.exists()


def test_quick_validate_ignores_dedicated_env_overrides():
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.update(
        {
            "HENRY_IMAGE_BASE_URL": "https://images.example/v1",
            "HENRY_IMAGE_API_KEY": "sk-test-dedicated",
            "HENRY_IMAGE_MODEL": "gpt-image-2",
            "HENRY_IMAGE_IMAGE_MODEL": "gpt-image-2",
        }
    )
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "quick_validate"],
        cwd=root,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    envelope = json.loads(proc.stdout)
    assert envelope["ok"] is True
    assert envelope["status"] == "completed"


if __name__ == "__main__":
    tests = [
        test_candidate_policy_filters_base_url_candidates,
        test_dedicated_henry_image_base_url_wins_over_codex_candidates,
        test_windows_user_env_fallback_when_process_env_missing,
        test_request_finish_and_failure_taxonomy_are_reported,
        test_route_auto_does_not_fallback_for_blocked_failure_categories,
        test_batch_resume_skip_existing_result_jsonl_and_max_images,
        test_job_list_cleanup_and_watch,
        test_quick_validate_ignores_dedicated_env_overrides,
    ]
    for test in tests:
        test()
    print(f"{len(tests)} p0/p1 tests passed")
