import argparse
import contextlib
import importlib.util
import io
import json
import sys
import tempfile
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "henry_image.py"


def load_module():
    spec = importlib.util.spec_from_file_location("henry_image_workflow_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@contextlib.contextmanager
def patched(obj, name, value):
    old = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield
    finally:
        setattr(obj, name, old)


def base_args(**overrides):
    data = dict(
        prompt="A simple blue ceramic cup on a white table",
        prompt_file=None,
        size="1024x1024",
        quality="medium",
        model="gpt-5",
        image_model="gpt-image-2",
        base_url="https://api.openai.com/v1",
        base_url_source="cli",
        api_key_env=None,
        route="responses",
        candidate_policy="auto",
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
        background_job=False,
    )
    data.update(overrides)
    return argparse.Namespace(**data)


def test_command_generate_dry_run_emits_workflow_metadata():
    mod = load_module()
    with tempfile.TemporaryDirectory() as tmp:
        cache_root = Path(tmp) / ".cache"
        args = base_args(dry_run=True, out=str(Path(tmp) / "preview.png"))
        stdout = io.StringIO()
        with patched(mod, "SKILL_CACHE_ROOT", cache_root):
            with contextlib.redirect_stdout(stdout):
                code = mod.command_generate(args)
        assert code == 0
        payload = json.loads(stdout.getvalue())
        workflow = payload["metadata"]["workflow"]
        assert workflow["mode"] == "generate"
        assert workflow["stage"] == "preview"
        assert workflow["next_action"]
        assert "generate" in workflow["replay_command"]
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
                "auth_profiles",
                lambda *_args, **_kwargs: [
                    mod.AuthProfile(
                        "test-secret",
                        "env:test",
                        "bearer",
                        {"Authorization": "Bearer test-secret"},
                        {},
                        {},
                        {},
                        "openai",
                        "workflow-test",
                    )
                ],
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


if __name__ == "__main__":
    tests = [
        test_command_generate_dry_run_emits_workflow_metadata,
        test_command_generate_success_persists_workflow_profile,
    ]
    for test in tests:
        test()
    print(f"{len(tests)} workflow tests passed")
