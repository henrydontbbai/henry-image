import argparse
import contextlib
import io
import json
import os
import tempfile
from pathlib import Path
import sys

import pytest

from helpers import load_module, patched


def base_args(**overrides):
    data = dict(
        prompt="A simple blue ceramic cup on a white table",
        prompt_file=None,
        image=[],
        image_file_id=[],
        mask=None,
        mask_file_id=None,
        size="1024x1024",
        quality="medium",
        model="response-service",
        image_model="image-service",
        base_url="https://images.example/v1",
        api_key_env=None,
        route="responses",
        n=1,
        output_format="png",
        images_response_format="auto",
        output_compression=None,
        timeout=1,
        dry_run=False,
        force=True,
        out="output/imagegen/workflow-test.png",
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


def test_command_generate_dry_run_emits_workflow_metadata():
    mod = load_module()
    with tempfile.TemporaryDirectory() as tmp:
        cache_root = Path(tmp) / ".cache"
        args = base_args(dry_run=True, out=str(Path(tmp) / "preview.png"))
        stdout = io.StringIO()
        previous_key = os.environ.pop("HENRY_IMAGE_API_KEY", None)
        with patched(mod, "SKILL_CACHE_ROOT", cache_root):
            with contextlib.redirect_stdout(stdout):
                try:
                    code = mod.command_generate(args)
                finally:
                    if previous_key is not None:
                        os.environ["HENRY_IMAGE_API_KEY"] = previous_key
        assert code == 0
        payload = json.loads(stdout.getvalue())
        workflow = payload["metadata"]["workflow"]
        assert workflow["mode"] == "generate"
        assert workflow["stage"] == "preview"
        assert workflow["next_action"]
        assert "scripts/henry_image.py generate" in workflow["replay_command"]
        assert payload["metadata"]["auth_source"] == "not_required_for_dry_run"
        assert payload["metadata"]["workflow_profile"]["version"] == 1
        assert not (cache_root / "workflow-profile.json").exists()


def test_command_generate_success_persists_workflow_profile():
    mod = load_module()
    fake_result = mod.ApiResult(
        True,
        200,
        {"output": [{"type": "image_generation_call", "result": "iVBORw0KGgpmYWtl"}]},
        None,
        "req-workflow",
        15,
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cache_root = root / ".cache"
        args = base_args(out=str(root / "generated.png"))
        stdout = io.StringIO()
        profile_path = cache_root / "workflow-profile.json"
        with patched(mod, "SKILL_CACHE_ROOT", cache_root):
            with patched(
                mod,
                "resolve_api_key",
                lambda *_args, **_kwargs: ("test-secret", "HENRY_IMAGE_API_KEY"),
            ):
                with patched(mod, "request_json", lambda *_args, **_kwargs: fake_result):
                    with contextlib.redirect_stdout(stdout):
                        code = mod.command_generate(args)
        assert code == 0
        payload = json.loads(stdout.getvalue())
        workflow = payload["metadata"]["workflow"]
        assert workflow["mode"] == "generate"
        assert workflow["stage"] == "review"
        assert workflow["source_output"] is None
        assert profile_path.exists()
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        assert profile["last_mode"] == "generate"
        assert profile["default_output_dir"] == str(root)
        assert profile["default_size"] == "1024x1024"
        assert profile["default_quality"] == "medium"
        assert payload["metadata"]["workflow_profile"]["last_mode"] == "generate"
        assert "codex_access" not in payload["metadata"]
        assert "candidate_attempts" not in payload["metadata"]


@pytest.mark.parametrize(
    "profile_error",
    [
        OSError("cache unavailable"),
        UnicodeEncodeError("utf-8", "\ud800", 0, 1, "surrogates not allowed"),
    ],
)
def test_command_generate_keeps_successful_output_when_workflow_profile_write_fails(profile_error):
    mod = load_module()
    workflow_module = sys.modules[mod.attach_workflow_metadata.__module__]
    fake_result = mod.ApiResult(
        True,
        200,
        {"output": [{"type": "image_generation_call", "result": "iVBORw0KGgpmYWtl"}]},
        None,
        "req-workflow-cache-failure",
        15,
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cache_root = root / ".cache"
        output_path = root / "generated.png"
        args = base_args(out=str(output_path))
        stdout = io.StringIO()
        with patched(mod, "SKILL_CACHE_ROOT", cache_root):
            with patched(
                mod,
                "resolve_api_key",
                lambda *_args, **_kwargs: ("test-secret", "HENRY_IMAGE_API_KEY"),
            ):
                with patched(mod, "request_json", lambda *_args, **_kwargs: fake_result):
                    with patched(
                        workflow_module,
                        "update_workflow_profile",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(profile_error),
                    ):
                        with contextlib.redirect_stdout(stdout):
                            code = mod.command_generate(args)

        payload = json.loads(stdout.getvalue())
        assert code == 0
        assert payload["ok"] is True
        assert output_path.exists()
        assert (root / "generated.png.json").exists()
        assert payload["metadata"]["workflow_profile"]["version"] == 1
        assert payload["metadata"]["workflow_profile_error"] == "Workflow profile cache could not be updated."


def test_command_edit_dry_run_replay_command_keeps_edit_inputs():
    mod = load_module()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cache_root = root / ".cache"
        image_path = root / "source.png"
        mask_path = root / "mask.png"
        image_path.write_bytes(b"source")
        mask_path.write_bytes(b"mask")
        args = base_args(
            dry_run=True,
            route="auto",
            image=[str(image_path)],
            image_file_id=["file-source-1"],
            mask=str(mask_path),
            mask_file_id="file-mask-1",
            out=str(root / "edited.png"),
        )
        stdout = io.StringIO()
        with patched(mod, "SKILL_CACHE_ROOT", cache_root):
            with patched(
                mod,
                "resolve_api_key",
                lambda *_args, **_kwargs: ("test-secret", "HENRY_IMAGE_API_KEY"),
            ):
                with contextlib.redirect_stdout(stdout):
                    code = mod.command_edit(args)
        assert code == 0
        payload = json.loads(stdout.getvalue())
        replay_command = payload["metadata"]["workflow"]["replay_command"]
        assert "scripts/henry_image.py edit" in replay_command
        assert "--image " in replay_command
        assert str(image_path) in replay_command
        assert "--image-file-id file-source-1" in replay_command
        assert "--mask " in replay_command
        assert str(mask_path) in replay_command
        assert "--mask-file-id file-mask-1" in replay_command


def test_replay_command_keeps_reliability_and_batch_arguments():
    mod = load_module()
    workflow_module = sys.modules[mod.attach_workflow_metadata.__module__]
    args = base_args(
        prompt="Henry's cup",
        route="images",
        n=3,
        timeout=42,
        images_response_format="url",
        output_compression=81,
        force=True,
        batch_input=r"C:\input files\tasks.jsonl",
        out_dir=r"C:\output files\batch",
    )

    replay_command = workflow_module.build_replay_command(
        args,
        args.out_dir,
        "batch",
    )

    for expected in (
        "--n 3",
        "--timeout 42",
        "--images-response-format url",
        "--output-compression 81",
        "--force",
        "--batch-input",
        "tasks.jsonl",
        "--out-dir",
    ):
        assert expected in replay_command
    assert "secret-key" not in replay_command


def test_windows_replay_command_uses_powershell_single_quote_escaping():
    mod = load_module()
    workflow_module = sys.modules[mod.attach_workflow_metadata.__module__]
    args = base_args(prompt="Henry's cup", force=False)

    with patched(workflow_module.os, "name", "nt"):
        replay_command = workflow_module.build_replay_command(
            args,
            r"C:\output files\cup.png",
            "generate",
        )

    assert "'Henry''s cup'" in replay_command
    assert "'C:\\output files\\cup.png'" in replay_command


def test_windows_replay_command_invokes_quoted_python_executable():
    mod = load_module()
    workflow_module = sys.modules[mod.attach_workflow_metadata.__module__]
    args = base_args(prompt="test")

    with patched(workflow_module.sys, "executable", r"C:\Program Files\Python\python.exe"):
        with patched(workflow_module.os, "name", "nt"):
            replay_command = workflow_module.build_replay_command(
                args,
                r"C:\output files\cup.png",
                "generate",
            )

    assert replay_command.startswith("& 'C:\\Program Files\\Python\\python.exe' scripts/henry_image.py generate")


def test_replay_command_uses_the_current_python_executable():
    mod = load_module()
    workflow_module = sys.modules[mod.attach_workflow_metadata.__module__]
    args = base_args(prompt="test")

    with patched(workflow_module.sys, "executable", "/opt/python 3/bin/python3"):
        with patched(workflow_module.os, "name", "posix"):
            replay_command = workflow_module.build_replay_command(
                args,
                "/tmp/output.png",
                "generate",
            )

    assert replay_command.startswith("'/opt/python 3/bin/python3' scripts/henry_image.py generate")


if __name__ == "__main__":
    tests = [
        test_command_generate_dry_run_emits_workflow_metadata,
        test_command_generate_success_persists_workflow_profile,
        test_command_edit_dry_run_replay_command_keeps_edit_inputs,
        test_replay_command_keeps_reliability_and_batch_arguments,
        test_windows_replay_command_uses_powershell_single_quote_escaping,
    ]
    for test in tests:
        test()
    print(f"{len(tests)} workflow tests passed")
