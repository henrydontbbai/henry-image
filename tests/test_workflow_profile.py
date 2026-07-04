import argparse
import contextlib
import io
import json
import os
import tempfile
from pathlib import Path

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
        images_compat="auto",
        input_fidelity="auto",
        output_compression=None,
        background="auto",
        moderation="auto",
        partial_images=0,
        timeout=1,
        retries=0,
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
        assert workflow["replay_command"].startswith("python scripts/henry_image.py generate")
        assert payload["metadata"]["auth_source"] == "not_required_for_dry_run"
        assert payload["metadata"]["workflow_profile"]["version"] == 1
        assert not (cache_root / "workflow-profile.json").exists()


def test_command_generate_success_persists_workflow_profile():
    mod = load_module()
    fake_result = mod.ApiResult(
        True,
        200,
        {"output": [{"type": "image_generation_call", "result": "ZmFrZQ=="}]},
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
        assert replay_command.startswith("python scripts/henry_image.py edit")
        assert "--image " in replay_command
        assert str(image_path) in replay_command
        assert "--image-file-id file-source-1" in replay_command
        assert "--mask " in replay_command
        assert str(mask_path) in replay_command
        assert "--mask-file-id file-mask-1" in replay_command


if __name__ == "__main__":
    tests = [
        test_command_generate_dry_run_emits_workflow_metadata,
        test_command_generate_success_persists_workflow_profile,
        test_command_edit_dry_run_replay_command_keeps_edit_inputs,
    ]
    for test in tests:
        test()
    print(f"{len(tests)} workflow tests passed")
