import argparse
import contextlib
import importlib.util
import io
import json
import os
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "henry_image.py"


def load_module():
    spec = importlib.util.spec_from_file_location("henry_image_p1_6_under_test", SCRIPT)
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


@contextlib.contextmanager
def patched_env(**updates):
    old = {key: os.environ.get(key) for key in updates}
    for key, value in updates.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    try:
        yield
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def base_args(**overrides):
    data = dict(
        api_key_env=None,
        background="auto",
        base_url="https://api.openai.com/v1",
        base_url_source="cli",
        candidate_policy="auto",
        dry_run=False,
        force=True,
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
    data.update(overrides)
    return argparse.Namespace(**data)


def test_openai_default_auth_profile_uses_bearer_and_org_project_headers():
    mod = load_module()
    with patched_env(
        OPENAI_API_KEY="sk-openai-test-secret",
        OPENAI_ORG_ID="org-secret-test",
        OPENAI_PROJECT_ID="proj-secret-test",
    ):
        profiles = mod.auth_profiles("https://api.openai.com/v1", "cli", None, "responses")
    assert profiles[0].shape == "bearer"
    assert profiles[0].headers["Authorization"].startswith("Bearer ")
    assert profiles[0].headers["OpenAI-Organization"] == "org-secret-test"
    assert profiles[0].headers["OpenAI-Project"] == "proj-secret-test"
    summary = mod.auth_profile_summary(profiles[0])
    assert summary["auth_shape"] == "bearer"
    assert "Authorization" in summary["header_names"]
    assert "OpenAI-Organization" in summary["header_names"]
    assert "org-secret-test" not in json.dumps(mod.redact(summary), ensure_ascii=False)


def test_azure_base_url_auto_uses_api_key_header_and_api_version_query():
    mod = load_module()
    with patched(mod, "auth_candidates", lambda *_args, **_kwargs: [("azure-secret-key", "AZURE_OPENAI_API_KEY")]):
        profiles = mod.auth_profiles(
            "https://henry-resource.openai.azure.com/openai/deployments/img",
            "AZURE_OPENAI_ENDPOINT",
            None,
            "images",
        )
    assert profiles[0].shape == "api-key-header"
    assert profiles[0].headers["api-key"] == "azure-secret-key"
    assert profiles[0].query["api-version"] == mod.DEFAULT_AZURE_API_VERSION
    assert profiles[0].provider_family == "azure"
    assert "api-key" in mod.auth_profile_summary(profiles[0])["header_names"]
    assert "api-version" in mod.auth_profile_summary(profiles[0])["query_names"]


def test_azure_openai_v1_profile_allows_same_base_auth_shape_adaptation():
    mod = load_module()
    with patched(mod, "auth_candidates", lambda *_args, **_kwargs: [("azure-secret-key", "AZURE_OPENAI_API_KEY")]):
        profiles = mod.auth_profiles(
            "https://henry-resource.openai.azure.com/openai/v1",
            "AZURE_OPENAI_ENDPOINT",
            None,
            "responses",
    )
    assert [profile.shape for profile in profiles[:2]] == ["api-key-header", "bearer"]
    assert all(profile.provider_family == "azure" for profile in profiles[:2])
    assert profiles[0].query.get("api-version") == mod.DEFAULT_AZURE_API_VERSION


def test_local_relay_no_auth_is_first_and_does_not_send_global_key():
    mod = load_module()
    with patched_env(OPENAI_API_KEY="sk-local-should-not-be-first"):
        profiles = mod.auth_profiles("http://127.0.0.1:8787/v1", "LOCAL_RELAY_TEST", None, "responses")
    assert profiles[0].shape == "no-auth"
    assert profiles[0].headers == {}
    assert profiles[0].source == "local_relay:no_auth"
    assert all("Authorization" not in profile.headers for profile in profiles)
    assert all("sk-local-should-not-be-first" not in json.dumps(profile.headers) for profile in profiles)


def test_local_relay_allows_explicit_command_key_after_no_auth():
    mod = load_module()
    with patched_env(HENRY_LOCAL_RELAY_KEY="local-explicit-key"):
        profiles = mod.auth_profiles("http://127.0.0.1:8787/v1", "LOCAL_RELAY_TEST", "HENRY_LOCAL_RELAY_KEY", "responses")
    assert profiles[0].shape == "no-auth"
    assert any(profile.source == "HENRY_LOCAL_RELAY_KEY" and profile.shape == "bearer" for profile in profiles[1:])


def test_codex_provider_configured_headers_and_query_create_auth_profile_without_env_key():
    mod = load_module()
    with patched(mod, "provider_config_headers", lambda _source: (
        {"Authorization": "Bearer codex-header-secret"},
        {"Authorization": "codex_config:headers"},
    )):
        with patched(mod, "provider_config_query", lambda _source: (
            {"api-version": "2024-10-21", "custom_token": "codex-query-secret"},
            {"api-version": "codex_config:api_version", "custom_token": "codex_config:query"},
        )):
            with patched(mod, "auth_candidates", lambda *_args, **_kwargs: []):
                profiles = mod.auth_profiles("https://router.example/v1", "codex_config:router", None, "responses")
    assert profiles
    assert profiles[0].shape == "bearer"
    assert profiles[0].source == "codex_config:headers"
    summary = mod.auth_profile_summary(profiles[0])
    assert "Authorization" in summary["header_names"]
    assert "custom_token" in summary["query_names"]
    assert "codex-header-secret" not in json.dumps(mod.redact(summary), ensure_ascii=False)
    assert "codex-query-secret" not in json.dumps(mod.redact(summary), ensure_ascii=False)


def test_run_route_request_switches_auth_shape_on_401_same_base_url_only():
    mod = load_module()
    args = base_args(base_url="https://api.openai.com/v1", base_url_source="cli")
    calls = []

    def fake_request_json(url, api_key, payload, retries, timeout, auth_profile=None):
        calls.append((url, auth_profile.shape, dict(auth_profile.headers), dict(auth_profile.query)))
        if len(calls) == 1:
            return mod.ApiResult(False, 401, None, {"status": 401, "code": "invalid_api_key", "message": "bad key"}, "req-1", 10)
        return mod.ApiResult(True, 200, {"output": [{"type": "image_generation_call", "result": "ZmFrZQ=="}]}, None, "req-2", 20)

    with patched(mod, "auth_profiles", lambda *_args, **_kwargs: [
        mod.AuthProfile("sk-bad", "env:bad", "bearer", {"Authorization": "Bearer sk-bad"}, {}, {}, {}, "openai", "test-bearer"),
        mod.AuthProfile("good-key", "env:good", "api-key-header", {"api-key": "good-key"}, {}, {}, {}, "openai", "test-api-key"),
    ]):
        with patched(mod, "request_json", fake_request_json):
            with patched(mod, "write_images", lambda *_args, **_kwargs: [{"index": 1, "path": "out.png", "bytes": 4, "format": "png"}]):
                with patched(mod, "write_manifest", lambda *_args, **_kwargs: "out.png.json"):
                    result = mod.run_route_request(route="responses", command="henry.generate", args=args, payload={"input": "x", "tools": []}, prompt="x", out="out.png")
    assert result["ok"] is True
    assert [call[1] for call in calls] == ["bearer", "api-key-header"]
    assert result["metadata"]["auth_shape"] == "api-key-header"
    assert len(result["metadata"]["auth_attempts"]) == 2


def test_strict_policy_keeps_only_first_auth_profile():
    mod = load_module()
    args = base_args(candidate_policy="strict")
    calls = []

    def fake_request_json(url, api_key, payload, retries, timeout, auth_profile=None):
        calls.append(auth_profile.shape)
        return mod.ApiResult(False, 401, None, {"status": 401, "code": "invalid_api_key", "message": "bad key"}, "req-1", 10)

    with patched(mod, "auth_profiles", lambda *_args, **_kwargs: [
        mod.AuthProfile("sk-bad", "env:bad", "bearer", {"Authorization": "Bearer sk-bad"}, {}, {}, {}, "openai", "test-bearer"),
        mod.AuthProfile("good-key", "env:good", "api-key-header", {"api-key": "good-key"}, {}, {}, {}, "openai", "test-api-key"),
    ]):
        with patched(mod, "request_json", fake_request_json):
            result = mod.run_route_request(route="responses", command="henry.generate", args=args, payload={"input": "x", "tools": []}, prompt="x", out="out.png")
    assert calls == ["bearer"]
    assert result["status"] == "invalid_credentials"


def test_rate_limit_does_not_try_next_auth_profile():
    mod = load_module()
    args = base_args()
    calls = []

    def fake_request_json(url, api_key, payload, retries, timeout, auth_profile=None):
        calls.append(auth_profile.shape)
        return mod.ApiResult(False, 429, None, {"status": 429, "code": "rate_limit_exceeded", "message": "rate limit"}, "req-1", 10)

    with patched(mod, "auth_profiles", lambda *_args, **_kwargs: [
        mod.AuthProfile("first", "env:first", "bearer", {"Authorization": "Bearer first"}, {}, {}, {}, "openai", "test-first"),
        mod.AuthProfile("second", "env:second", "api-key-header", {"api-key": "second"}, {}, {}, {}, "openai", "test-second"),
    ]):
        with patched(mod, "request_json", fake_request_json):
            result = mod.run_route_request(route="responses", command="henry.generate", args=args, payload={"input": "x", "tools": []}, prompt="x", out="out.png")
    assert calls == ["bearer"]
    assert result["status"] == "rate_limited"


def test_request_events_include_adaptive_auth_fields():
    mod = load_module()
    args = base_args()
    fake_result = mod.ApiResult(False, 429, None, {"status": 429, "code": "rate_limit_exceeded", "message": "rate limit"}, "req-test", 123)
    stderr = io.StringIO()
    profile = mod.AuthProfile("secret", "env:test", "api-key-header", {"api-key": "secret"}, {"api-version": "2024-10-21"}, {}, {}, "azure", "azure-like")
    with patched(mod, "auth_profiles", lambda *_args, **_kwargs: [profile]):
        with patched(mod, "request_json", lambda *_args, **_kwargs: fake_result):
            with contextlib.redirect_stderr(stderr):
                mod.run_route_request(route="responses", command="henry.generate", args=args, payload={"input": "x", "tools": []}, prompt="x", out="out.png")
    events = [json.loads(line) for line in stderr.getvalue().splitlines()]
    start = next(event for event in events if event["event"] == "request_start")
    finish = next(event for event in events if event["event"] == "request_finish")
    assert start["auth_shape"] == "api-key-header"
    assert start["header_names"] == ["api-key"]
    assert start["query_names"] == ["api-version"]
    assert finish["provider_family"] == "azure"
    assert finish["adaptive_reason"] == "azure-like"
    assert "secret" not in stderr.getvalue()


def test_dry_run_metadata_shows_redacted_adaptive_auth_plan():
    mod = load_module()
    args = base_args(dry_run=True)
    profile = mod.AuthProfile("super-secret", "env:test", "api-key-header", {"api-key": "super-secret"}, {"api-version": "2024-10-21"}, {}, {}, "azure", "test")
    with patched(mod, "auth_profiles", lambda *_args, **_kwargs: [profile]):
        result = mod.run_route_request(route="responses", command="henry.generate", args=args, payload={"input": "x", "tools": []}, prompt="x", out="out.png")
    metadata = result["metadata"]
    assert metadata["auth_plan"][0]["auth_shape"] == "api-key-header"
    assert metadata["auth_plan"][0]["header_names"] == ["api-key"]
    assert metadata["auth_shape"] == "api-key-header"
    assert metadata["header_names"] == ["api-key"]
    assert metadata["query_names"] == ["api-version"]
    attempt = mod.summarize_attempt(result, args.base_url, args.base_url_source, args.route)
    assert attempt["auth_shape"] == "api-key-header"
    assert attempt["header_names"] == ["api-key"]
    assert attempt["query_names"] == ["api-version"]
    assert attempt["adaptive_reason"] == "test"
    mod.attach_attempt_metadata(result, [attempt])
    candidate_attempt = result["metadata"]["candidate_attempts"][0]
    route_attempt = result["metadata"]["route_attempts"][0]
    for item in (candidate_attempt, route_attempt):
        assert item["auth_shape"] == "api-key-header"
        assert item["header_names"] == ["api-key"]
        assert item["query_names"] == ["api-version"]
        assert item["adaptive_reason"] == "test"
    assert "super-secret" not in json.dumps(result, ensure_ascii=False)



def test_request_json_builds_auth_profile_headers_and_query(monkeypatch=None):
    mod = load_module()
    captured = {}

    class FakeResponse:
        status = 200
        headers = {"x-request-id": "req-header"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"ok":true}'

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.header_items())
        captured["timeout"] = timeout
        return FakeResponse()

    profile = mod.AuthProfile(
        "azure-secret-key",
        "AZURE_OPENAI_API_KEY",
        "api-key-header",
        {"api-key": "azure-secret-key"},
        {"api-version": "2024-10-21"},
        {"api-key": "AZURE_OPENAI_API_KEY"},
        {"api-version": "default"},
        "azure",
        "Azure/AOAI-like base URL",
    )
    with patched(mod.request, "urlopen", fake_urlopen):
        result = mod.request_json("https://resource.openai.azure.com/openai/images/generations", None, {"prompt": "x"}, 0, 3, auth_profile=profile)
    assert result.ok is True
    assert "api-version=2024-10-21" in captured["url"]
    assert captured["headers"].get("Api-key") == "azure-secret-key"
    assert "Authorization" not in captured["headers"]


def test_invalid_credentials_do_not_fallback_to_next_base_url():
    mod = load_module()
    calls = []

    def fake_run_route_request(*, route, command, args, payload, prompt, out, extra_metadata=None):
        calls.append((args.base_url, route))
        return mod.envelope(
            ok=False,
            command=command,
            status="invalid_credentials",
            provider={"type": "fake"},
            error_obj={"status": 401, "code": "invalid_api_key", "category": "invalid_credentials", "message": "bad key"},
            metadata={"route": route, "base_url_source": args.base_url_source},
        )

    args = argparse.Namespace(route="auto", base_url=None, candidate_policy="auto")
    with patched(mod, "policy_base_url_candidates", lambda _args: [("https://one.example/v1", "one"), ("https://two.example/v1", "two")]):
        with patched(mod, "run_route_request", fake_run_route_request):
            result = mod.run_request(command="henry.generate", args=args, payload={}, prompt="x", out="out.png")
    assert calls == [("https://one.example/v1", "responses")]
    assert result["status"] == "invalid_credentials"


def test_openai_org_project_values_are_redacted_from_raw_strings():
    mod = load_module()
    with patched_env(
        OPENAI_API_KEY="sk-redact-test-secret",
        OPENAI_ORG_ID="org-redact-secret",
        OPENAI_PROJECT_ID="proj-redact-secret",
    ):
        text = mod.redact("Authorization: Bearer sk-redact-test-secret OpenAI-Organization org-redact-secret OpenAI-Project proj-redact-secret")
    assert "sk-redact-test-secret" not in text
    assert "org-redact-secret" not in text
    assert "proj-redact-secret" not in text
    assert text.count("[REDACTED_SECRET]") >= 3


def test_header_and_query_like_secrets_are_redacted_from_raw_strings():
    mod = load_module()
    text = mod.redact(
        '{"api-key":"azure-secret-value","OpenAI-Project":"proj-secret-value","custom":"safe"} '
        'x-api-key=relay-secret-value'
    )
    assert "azure-secret-value" not in text
    assert "proj-secret-value" not in text
    assert "relay-secret-value" not in text
    assert "safe" in text



def test_azure_profiles_prefer_azure_key_when_multiple_env_keys_exist():
    mod = load_module()
    with patched_env(OPENAI_API_KEY="sk-openai-not-for-azure", AZURE_OPENAI_API_KEY="azure-correct-key"):
        profiles = mod.auth_profiles("https://resource.openai.azure.com/openai/deployments/img", "AZURE_OPENAI_ENDPOINT", None, "images")
    assert profiles[0].source == "AZURE_OPENAI_API_KEY"
    assert profiles[0].shape == "api-key-header"
    assert profiles[0].headers["api-key"] == "azure-correct-key"


if __name__ == "__main__":
    tests = [
        test_openai_default_auth_profile_uses_bearer_and_org_project_headers,
        test_azure_base_url_auto_uses_api_key_header_and_api_version_query,
        test_azure_openai_v1_profile_allows_same_base_auth_shape_adaptation,
        test_local_relay_no_auth_is_first_and_does_not_send_global_key,
        test_local_relay_allows_explicit_command_key_after_no_auth,
        test_codex_provider_configured_headers_and_query_create_auth_profile_without_env_key,
        test_run_route_request_switches_auth_shape_on_401_same_base_url_only,
        test_strict_policy_keeps_only_first_auth_profile,
        test_rate_limit_does_not_try_next_auth_profile,
        test_request_events_include_adaptive_auth_fields,
        test_dry_run_metadata_shows_redacted_adaptive_auth_plan,
        test_request_json_builds_auth_profile_headers_and_query,
        test_invalid_credentials_do_not_fallback_to_next_base_url,
        test_openai_org_project_values_are_redacted_from_raw_strings,
        test_header_and_query_like_secrets_are_redacted_from_raw_strings,
        test_azure_profiles_prefer_azure_key_when_multiple_env_keys_exist,
    ]
    for test in tests:
        test()
    print(f"{len(tests)} p1.6 adaptive auth tests passed")
