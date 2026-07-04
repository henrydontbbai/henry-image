import argparse
import base64
import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path
from urllib import error

from helpers import load_module, patched, patched_env, run_cli


def marker(*parts):
    return "".join(parts)


def base_args(**overrides):
    data = dict(
        prompt="A clean product photo of a ceramic cup",
        prompt_file=None,
        image=[],
        image_file_id=[],
        mask=None,
        mask_file_id=None,
        size="1024x1024",
        quality="medium",
        model=None,
        image_model=None,
        base_url=None,
        api_key_env=None,
        route="responses",
        n=1,
        output_format="png",
        images_response_format="auto",
        images_compat="auto",
        input_fidelity="auto",
        output_compression=None,
        background="auto",
        moderation="auto",
        partial_images=0,
        timeout=5,
        retries=0,
        dry_run=False,
        force=True,
        out="output/imagegen/test.png",
        out_dir="output/imagegen/batch",
        background_job=False,
        batch_input=None,
        negative_prompt="",
        use_case="auto",
        review_template="auto",
        platform="generic",
        package_version="generic",
        explain=False,
    )
    data.update(overrides)
    return argparse.Namespace(**data)


def read_payload(code, stdout):
    assert code in {0, 1}, stdout
    return json.loads(stdout)


def data_url(raw: bytes, mime: str = "image/png") -> str:
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{encoded}"


class FakeResponse:
    def __init__(self, *, status=200, body=b"", read_exc=None, headers=None):
        self.status = status
        self._body = body
        self._read_exc = read_exc
        self.headers = headers or {}

    def read(self):
        if self._read_exc is not None:
            raise self._read_exc
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_generate_responses_requires_explicit_model():
    mod = load_module()
    args = base_args(route="responses", image_model="image-service")
    stdout = io.StringIO()
    with patched_env(
        HENRY_IMAGE_BASE_URL="https://images.example/v1",
        HENRY_IMAGE_API_KEY="secret-key",
        HENRY_IMAGE_MODEL=None,
        HENRY_IMAGE_IMAGE_MODEL=None,
    ):
        with contextlib.redirect_stdout(stdout):
            code = mod.command_generate(args)
    payload = read_payload(code, stdout.getvalue())
    assert code == 1
    assert payload["status"] == "validation_error"
    assert "model is required for route responses" in payload["error"]["message"].lower()


def test_generate_images_requires_explicit_image_model():
    mod = load_module()
    args = base_args(route="images", model="response-service")
    stdout = io.StringIO()
    with patched_env(
        HENRY_IMAGE_BASE_URL="https://images.example/v1",
        HENRY_IMAGE_API_KEY="secret-key",
        HENRY_IMAGE_MODEL=None,
        HENRY_IMAGE_IMAGE_MODEL=None,
    ):
        with contextlib.redirect_stdout(stdout):
            code = mod.command_generate(args)
    payload = read_payload(code, stdout.getvalue())
    assert code == 1
    assert payload["status"] == "validation_error"
    assert "image-model is required for route images" in payload["error"]["message"].lower()


def test_generate_auto_requires_both_models():
    mod = load_module()
    args = base_args(route="auto", model="response-service", image_model=None)
    stdout = io.StringIO()
    with patched_env(
        HENRY_IMAGE_BASE_URL="https://images.example/v1",
        HENRY_IMAGE_API_KEY="secret-key",
        HENRY_IMAGE_MODEL=None,
        HENRY_IMAGE_IMAGE_MODEL=None,
    ):
        with contextlib.redirect_stdout(stdout):
            code = mod.command_generate(args)
    payload = read_payload(code, stdout.getvalue())
    assert code == 1
    assert payload["status"] == "validation_error"
    assert "both model and image-model are required for route auto" in payload["error"]["message"].lower()


def test_external_aliases_are_not_used_for_api_key_resolution():
    mod = load_module()
    with patched_env(
        HENRY_IMAGE_API_KEY=None,
        **{
            marker("OPEN", "AI_API_KEY"): "legacy-key",
            marker("AZ", "URE_OPEN", "AI_API_KEY"): "azure-key",
        },
    ):
        assert mod.resolve_api_key(None) == (None, None)


def test_explicit_api_key_env_overrides_default_henry_key():
    mod = load_module()
    with patched_env(HENRY_IMAGE_API_KEY="default-key", CUSTOM_HENRY_KEY="explicit-key"):
        assert mod.resolve_api_key("CUSTOM_HENRY_KEY") == ("explicit-key", "CUSTOM_HENRY_KEY")


def test_removed_public_commands_and_flags_are_hidden():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        top = run_cli(["--help"], root)
        assert top.returncode == 0, top.stderr + top.stdout
        assert marker("probe-image-", "providers") not in top.stdout
        assert marker("provider-", "cache") not in top.stdout

        gen = run_cli(["generate", "--help"], root)
        assert gen.returncode == 0, gen.stderr + gen.stdout
        assert "--" + marker("candidate-", "policy") not in gen.stdout


def test_prompt_package_is_generic_only():
    mod = load_module()
    args = base_args(
        route="responses",
        model="response-service",
        image_model="image-service",
        out="output/imagegen/prompt-package.json",
    )
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        code = mod.command_prompt(args)
    payload = read_payload(code, stdout.getvalue())
    assert code == 0
    package = payload["outputs"][0]["package"]
    package_text = json.dumps(package, ensure_ascii=False)
    for banned in (
        marker("Fl", "ux"),
        marker("SD", "XL"),
        marker("Mid", "journey"),
        marker("Comfy", "UI"),
        marker("open", "ai"),
    ):
        assert banned not in package_text


def test_build_edit_inputs_decode_inline_data_urls_for_multipart_uploads():
    mod = load_module()
    source_bytes = b"source-image"
    mask_bytes = b"mask-image"
    source_url = data_url(source_bytes)
    mask_url = data_url(mask_bytes)
    args = base_args(image=[source_url], mask=mask_url)

    response_inputs, multipart_files = mod.build_edit_inputs(args)

    assert response_inputs[0]["image"] == source_url
    assert any(item.get("role") == "mask" and item["image"] == mask_url for item in response_inputs)
    assert ("image", "inline.png", source_bytes) in multipart_files
    assert ("mask", "inline.png", mask_bytes) in multipart_files


def test_probe_live_timeout_returns_structured_error_instead_of_traceback():
    mod = load_module()
    request_module = sys.modules[mod.request_json.__module__]
    args = base_args(route="responses", model="response-service", image_model="image-service", live=True)
    stdout = io.StringIO()

    def fake_urlopen(*_args, **_kwargs):
        raise TimeoutError("The read operation timed out")

    with patched(request_module.request, "urlopen", fake_urlopen):
        with patched_env(
            HENRY_IMAGE_BASE_URL="https://images.example/v1",
            HENRY_IMAGE_API_KEY="secret-key",
        ):
            with contextlib.redirect_stdout(stdout):
                code = mod.command_probe(args)

    payload = read_payload(code, stdout.getvalue())
    assert code == 1
    assert payload["status"] == "timeout"
    assert payload["error"]["category"] == "timeout"
    assert "timed out" in payload["error"]["message"].lower()


def test_edit_remote_input_timeout_returns_structured_error():
    mod = load_module()
    request_module = sys.modules[mod.request_json.__module__]
    args = base_args(
        route="responses",
        model="response-service",
        image_model="image-service",
        image=["https://example.com/source.png"],
    )
    stdout = io.StringIO()

    def fake_urlopen(*_args, **_kwargs):
        raise TimeoutError("The read operation timed out")

    with patched(request_module.request, "urlopen", fake_urlopen):
        with contextlib.redirect_stdout(stdout):
            code = mod.command_edit(args)

    payload = read_payload(code, stdout.getvalue())
    assert code == 1
    assert payload["status"] == "timeout"
    assert payload["error"]["category"] == "timeout"
    assert "timed out" in payload["error"]["message"].lower()


def test_probe_live_read_timeout_returns_structured_error():
    mod = load_module()
    request_module = sys.modules[mod.request_json.__module__]
    args = base_args(route="responses", model="response-service", image_model="image-service", live=True)
    stdout = io.StringIO()

    def fake_urlopen(*_args, **_kwargs):
        return FakeResponse(read_exc=TimeoutError("The read operation timed out"))

    with patched(request_module.request, "urlopen", fake_urlopen):
        with patched_env(
            HENRY_IMAGE_BASE_URL="https://images.example/v1",
            HENRY_IMAGE_API_KEY="secret-key",
        ):
            with contextlib.redirect_stdout(stdout):
                code = mod.command_probe(args)

    payload = read_payload(code, stdout.getvalue())
    assert code == 1
    assert payload["status"] == "timeout"
    assert payload["error"]["category"] == "timeout"
    assert "timed out" in payload["error"]["message"].lower()


def test_edit_remote_input_http_error_returns_structured_error():
    mod = load_module()
    request_module = sys.modules[mod.request_json.__module__]
    args = base_args(
        route="responses",
        model="response-service",
        image_model="image-service",
        image=["https://example.com/source.png"],
    )
    stdout = io.StringIO()

    def fake_urlopen(*_args, **_kwargs):
        raise error.HTTPError(
            url="https://example.com/source.png",
            code=404,
            msg="Not Found",
            hdrs={},
            fp=io.BytesIO(b"Not Found"),
        )

    with patched(request_module.request, "urlopen", fake_urlopen):
        with contextlib.redirect_stdout(stdout):
            code = mod.command_edit(args)

    payload = read_payload(code, stdout.getvalue())
    assert code == 1
    assert payload["status"] == "not_found"
    assert payload["error"]["category"] == "not_found"
    assert "not found" in payload["error"]["message"].lower()


def test_edit_images_route_read_timeout_returns_structured_error():
    mod = load_module()
    request_module = sys.modules[mod.request_json.__module__]
    args = base_args(
        route="images",
        image_model="image-service",
        image=[data_url(b"source-image")],
    )
    stdout = io.StringIO()

    def fake_urlopen(*_args, **_kwargs):
        return FakeResponse(read_exc=TimeoutError("The read operation timed out"))

    with patched(request_module.request, "urlopen", fake_urlopen):
        with patched_env(
            HENRY_IMAGE_BASE_URL="https://images.example/v1",
            HENRY_IMAGE_API_KEY="secret-key",
        ):
            with contextlib.redirect_stdout(stdout):
                code = mod.command_edit(args)

    payload = read_payload(code, stdout.getvalue())
    assert code == 1
    assert payload["status"] == "timeout"
    assert payload["error"]["category"] == "timeout"
    assert "timed out" in payload["error"]["message"].lower()


def test_generate_images_result_url_timeout_returns_structured_error():
    mod = load_module()
    request_module = sys.modules[mod.request_json.__module__]
    args = base_args(route="images", image_model="image-service")
    stdout = io.StringIO()

    def fake_request_json(*_args, **_kwargs):
        return mod.ApiResult(
            True,
            200,
            {"data": [{"url": "https://example.com/result.png"}]},
            None,
            "req-timeout",
            0,
        )

    def fake_urlopen(*_args, **_kwargs):
        return FakeResponse(read_exc=TimeoutError("The read operation timed out"))

    with patched(mod, "request_json", fake_request_json):
        with patched(request_module.request, "urlopen", fake_urlopen):
            with patched_env(
                HENRY_IMAGE_BASE_URL="https://images.example/v1",
                HENRY_IMAGE_API_KEY="secret-key",
            ):
                with contextlib.redirect_stdout(stdout):
                    code = mod.command_generate(args)

    payload = read_payload(code, stdout.getvalue())
    assert code == 1
    assert payload["status"] == "timeout"
    assert payload["error"]["category"] == "timeout"
    assert "timed out" in payload["error"]["message"].lower()


def test_generate_images_result_url_http_error_returns_structured_error():
    mod = load_module()
    request_module = sys.modules[mod.request_json.__module__]
    args = base_args(route="images", image_model="image-service")
    stdout = io.StringIO()

    def fake_request_json(*_args, **_kwargs):
        return mod.ApiResult(
            True,
            200,
            {"data": [{"url": "https://example.com/result.png"}]},
            None,
            "req-not-found",
            0,
        )

    def fake_urlopen(*_args, **_kwargs):
        raise error.HTTPError(
            url="https://example.com/result.png",
            code=404,
            msg="Not Found",
            hdrs={},
            fp=io.BytesIO(b"Not Found"),
        )

    with patched(mod, "request_json", fake_request_json):
        with patched(request_module.request, "urlopen", fake_urlopen):
            with patched_env(
                HENRY_IMAGE_BASE_URL="https://images.example/v1",
                HENRY_IMAGE_API_KEY="secret-key",
            ):
                with contextlib.redirect_stdout(stdout):
                    code = mod.command_generate(args)

    payload = read_payload(code, stdout.getvalue())
    assert code == 1
    assert payload["status"] == "not_found"
    assert payload["error"]["category"] == "not_found"
    assert "not found" in payload["error"]["message"].lower()


def test_generate_missing_prompt_returns_structured_validation_error():
    mod = load_module()
    args = base_args(
        prompt=None,
        prompt_file=None,
        route="responses",
        model="response-service",
        image_model="image-service",
    )
    stdout = io.StringIO()

    with contextlib.redirect_stdout(stdout):
        code = mod.command_generate(args)

    payload = read_payload(code, stdout.getvalue())
    assert code == 1
    assert payload["status"] == "validation_error"
    assert "missing prompt" in payload["error"]["message"].lower()


def test_generate_timeout_zero_returns_structured_validation_error():
    mod = load_module()
    args = base_args(
        route="responses",
        model="response-service",
        image_model="image-service",
        timeout=0,
    )
    stdout = io.StringIO()

    with contextlib.redirect_stdout(stdout):
        code = mod.command_generate(args)

    payload = read_payload(code, stdout.getvalue())
    assert code == 1
    assert payload["status"] == "validation_error"
    assert "timeout must be at least 1 second" in payload["error"]["message"].lower()


def test_probe_live_timeout_zero_returns_structured_validation_error():
    mod = load_module()
    args = base_args(
        route="responses",
        model="response-service",
        image_model="image-service",
        timeout=0,
        live=True,
    )
    stdout = io.StringIO()

    with patched_env(
        HENRY_IMAGE_BASE_URL="https://images.example/v1",
        HENRY_IMAGE_API_KEY="secret-key",
    ):
        with contextlib.redirect_stdout(stdout):
            code = mod.command_probe(args)

    payload = read_payload(code, stdout.getvalue())
    assert code == 1
    assert payload["status"] == "validation_error"
    assert payload["outputs"] == [{"type": "henry_probe", "live": True}]
    assert "timeout must be at least 1 second" in payload["error"]["message"].lower()


def test_batch_task_missing_prompt_returns_partial_failure_instead_of_traceback():
    mod = load_module()
    stdout = io.StringIO()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        batch_path = root / "batch.jsonl"
        batch_path.write_text("{}\n", encoding="utf-8")
        args = base_args(
            prompt=None,
            prompt_file=None,
            route="responses",
            model="response-service",
            image_model="image-service",
            batch_input=str(batch_path),
            out_dir=str(root / "out"),
        )

        with contextlib.redirect_stdout(stdout):
            code = mod.command_batch(args)

    payload = read_payload(code, stdout.getvalue())
    assert code == 1
    assert payload["status"] == "partial_failure"
    first_result = payload["outputs"][0]["results"][0]["result"]
    assert first_result["status"] == "validation_error"
    assert "missing prompt" in first_result["error"]["message"].lower()


def test_batch_non_object_task_returns_validation_error():
    mod = load_module()
    stdout = io.StringIO()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        batch_path = root / "batch.jsonl"
        batch_path.write_text("[]\n", encoding="utf-8")
        args = base_args(
            route="responses",
            model="response-service",
            image_model="image-service",
            batch_input=str(batch_path),
            out_dir=str(root / "out"),
        )

        with contextlib.redirect_stdout(stdout):
            code = mod.command_batch(args)

    payload = read_payload(code, stdout.getvalue())
    assert code == 1
    assert payload["status"] == "validation_error"
    assert "line 1" in payload["error"]["message"].lower()
    assert "json object" in payload["error"]["message"].lower()


def test_edit_invalid_inline_data_url_returns_validation_error():
    mod = load_module()
    args = base_args(
        route="responses",
        model="response-service",
        image_model="image-service",
        image=["data:image/png;base64,abc"],
    )
    stdout = io.StringIO()

    with contextlib.redirect_stdout(stdout):
        code = mod.command_edit(args)

    payload = read_payload(code, stdout.getvalue())
    assert code == 1
    assert payload["status"] == "validation_error"
    assert "invalid inline image data" in payload["error"]["message"].lower()


def test_auto_route_falls_back_from_responses_to_images_for_timeout():
    mod = load_module()
    stdout = io.StringIO()

    def fake_attempt_route(*, route, command, args, prompt, out, config, edit_inputs=None, multipart_files=None):
        if route == "responses":
            return mod.envelope(
                ok=False,
                command=command,
                status="timeout",
                provider={"type": "henry-remote-service", "route": route},
                error_obj={"code": "timeout", "message": "The read operation timed out."},
            )
        return mod.envelope(
            ok=True,
            command=command,
            status="completed",
            provider={"type": "henry-remote-service", "route": route},
            outputs=[],
        )

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        args = base_args(route="auto", model="response-service", image_model="image-service", out=str(root / "auto.png"))
        with patched(mod, "SKILL_CACHE_ROOT", root / ".cache"):
            with patched(mod, "attempt_route", fake_attempt_route):
                with patched_env(
                    HENRY_IMAGE_BASE_URL="https://images.example/v1",
                    HENRY_IMAGE_API_KEY="secret-key",
                ):
                    with contextlib.redirect_stdout(stdout):
                        code = mod.command_generate(args)

    payload = read_payload(code, stdout.getvalue())
    assert code == 0
    assert payload["ok"] is True
    assert payload["metadata"]["route_attempted"] == ["responses", "images"]
    assert payload["provider"]["route"] == "images"


def test_auto_route_does_not_fall_back_for_validation_error():
    mod = load_module()
    stdout = io.StringIO()

    def fake_attempt_route(*, route, command, args, prompt, out, config, edit_inputs=None, multipart_files=None):
        return mod.envelope(
            ok=False,
            command=command,
            status="validation_error",
            provider={"type": "henry-remote-service", "route": route},
            error_obj={"code": "invalid_request", "message": "Validation failed."},
        )

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        args = base_args(route="auto", model="response-service", image_model="image-service", out=str(root / "auto.png"))
        with patched(mod, "SKILL_CACHE_ROOT", root / ".cache"):
            with patched(mod, "attempt_route", fake_attempt_route):
                with patched_env(
                    HENRY_IMAGE_BASE_URL="https://images.example/v1",
                    HENRY_IMAGE_API_KEY="secret-key",
                ):
                    with contextlib.redirect_stdout(stdout):
                        code = mod.command_generate(args)

    payload = read_payload(code, stdout.getvalue())
    assert code == 1
    assert payload["metadata"]["route_attempted"] == ["responses"]
    assert payload["status"] == "validation_error"


def test_auto_route_falls_back_for_no_image_result():
    mod = load_module()
    stdout = io.StringIO()

    def fake_attempt_route(*, route, command, args, prompt, out, config, edit_inputs=None, multipart_files=None):
        if route == "responses":
            return mod.envelope(
                ok=False,
                command=command,
                status="no_image_result",
                provider={"type": "henry-remote-service", "route": route},
                error_obj={"code": "no_image_result", "message": "Remote service returned no image bytes."},
            )
        return mod.envelope(
            ok=True,
            command=command,
            status="completed",
            provider={"type": "henry-remote-service", "route": route},
            outputs=[],
        )

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        args = base_args(route="auto", model="response-service", image_model="image-service", out=str(root / "auto.png"))
        with patched(mod, "SKILL_CACHE_ROOT", root / ".cache"):
            with patched(mod, "attempt_route", fake_attempt_route):
                with patched_env(
                    HENRY_IMAGE_BASE_URL="https://images.example/v1",
                    HENRY_IMAGE_API_KEY="secret-key",
                ):
                    with contextlib.redirect_stdout(stdout):
                        code = mod.command_generate(args)

    payload = read_payload(code, stdout.getvalue())
    assert code == 0
    assert payload["metadata"]["route_attempted"] == ["responses", "images"]
    assert payload["provider"]["route"] == "images"


def test_quick_validate_reports_missing_required_files():
    mod = load_module()
    stdout = io.StringIO()

    def fake_subprocess_run(*_args, **_kwargs):
        return argparse.Namespace(returncode=0, stdout="", stderr="")

    with patched(mod, "missing_required_files", lambda: ["CONTRIBUTING.md"]):
        with patched(mod.subprocess, "run", fake_subprocess_run):
            with contextlib.redirect_stdout(stdout):
                code = mod.command_quick_validate(argparse.Namespace())

    payload = read_payload(code, stdout.getvalue())
    assert code == 1
    assert payload["status"] == "validation_error"
    assert "Missing required file: CONTRIBUTING.md" in payload["outputs"][0]["issues"]


def test_quick_validate_reports_removed_help_markers():
    mod = load_module()
    stdout = io.StringIO()

    def fake_subprocess_run(argv, **_kwargs):
        if "generate" in argv:
            return argparse.Namespace(returncode=0, stdout="--" + marker("candidate-", "policy"), stderr="")
        return argparse.Namespace(returncode=0, stdout=marker("probe-image-", "providers"), stderr="")

    with patched(mod, "missing_required_files", lambda: []):
        with patched(mod, "env_example_issues", lambda: []):
            with patched(mod, "readme_contract_issues", lambda: []):
                with patched(mod, "version_consistency_issues", lambda: []):
                    with patched(mod, "ci_workflow_issues", lambda: []):
                        with patched(mod, "release_process_issues", lambda: []):
                            with patched(mod, "disallowed_marker_issues", lambda: []):
                                with patched(mod.subprocess, "run", fake_subprocess_run):
                                    with contextlib.redirect_stdout(stdout):
                                        code = mod.command_quick_validate(argparse.Namespace())

    payload = read_payload(code, stdout.getvalue())
    assert code == 1
    assert payload["status"] == "validation_error"
    issues = payload["outputs"][0]["issues"]
    assert any("Removed command still appears in top-level help" in item for item in issues)
    assert any("Removed flag still appears in generate help" in item for item in issues)


def test_quick_validate_reports_disallowed_marker_issue():
    mod = load_module()
    stdout = io.StringIO()

    def fake_subprocess_run(*_args, **_kwargs):
        return argparse.Namespace(returncode=0, stdout="", stderr="")

    with patched(mod, "missing_required_files", lambda: []):
        with patched(mod, "env_example_issues", lambda: []):
            with patched(mod, "readme_contract_issues", lambda: []):
                with patched(mod, "version_consistency_issues", lambda: []):
                    with patched(mod, "ci_workflow_issues", lambda: []):
                        with patched(mod, "release_process_issues", lambda: []):
                            with patched(mod, "disallowed_marker_issues", lambda: ["README.md contains forbidden-marker"]):
                                with patched(mod.subprocess, "run", fake_subprocess_run):
                                    with contextlib.redirect_stdout(stdout):
                                        code = mod.command_quick_validate(argparse.Namespace())

    payload = read_payload(code, stdout.getvalue())
    assert code == 1
    assert payload["status"] == "validation_error"
    assert "README.md contains forbidden-marker" in payload["outputs"][0]["issues"]


def test_job_cleanup_invalid_duration_returns_validation_error():
    mod = load_module()
    stdout = io.StringIO()
    args = argparse.Namespace(jobs_dir=None, older_than="later")

    with contextlib.redirect_stdout(stdout):
        code = mod.command_job_cleanup(args)

    payload = read_payload(code, stdout.getvalue())
    assert code == 1
    assert payload["status"] == "validation_error"
    assert "duration must look like" in payload["error"]["message"].lower()


def test_quick_validate_passes_for_the_repo():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        proc = run_cli(["quick_validate"], root)
        assert proc.returncode == 0, proc.stderr + proc.stdout
        payload = json.loads(proc.stdout)
        assert payload["status"] == "completed"
        assert payload["outputs"][0]["issues"] == []
