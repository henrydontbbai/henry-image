import io
import json
from pathlib import Path
import sys
import tempfile
from urllib import error
from urllib import request

import pytest

from helpers import load_module, patched


class FakeResponse:
    def __init__(self, *, body=b"", read_exc=None, status=200, headers=None):
        self._body = io.BytesIO(body)
        self._read_exc = read_exc
        self.status = status
        self.headers = headers or {}

    def read(self, size=-1):
        if self._read_exc is not None:
            raise self._read_exc
        return self._body.read(size)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeOpener:
    def __init__(self, callback):
        self.callback = callback

    def open(self, target, timeout):
        return self.callback(target, timeout=timeout)


def load_request_module():
    mod = load_module()
    request_module = sys.modules[mod.request_json.__module__]
    return mod, request_module


def test_safe_urlopen_wraps_timeout_error():
    _mod, request_module = load_request_module()

    def fake_urlopen(*_args, **_kwargs):
        raise TimeoutError("The read operation timed out")

    with patched(request_module.request, "urlopen", fake_urlopen):
        try:
            request_module.safe_urlopen("https://images.example/v1", 5)
        except request_module.NetworkOperationError as exc:
            assert exc.error_data["code"] == "timeout"
            assert "timed out" in exc.error_data["message"].lower()
        else:
            raise AssertionError("Expected NetworkOperationError")


def test_safe_urlopen_with_policy_always_uses_controlled_opener():
    _mod, request_module = load_request_module()
    response = FakeResponse()
    calls = []

    class FakeOpener:
        def open(self, target, timeout):
            calls.append((target, timeout))
            return response

    def fail_urlopen(*_args, **_kwargs):
        raise AssertionError("Policy requests must not call the module urlopen directly")

    with patched(request_module.request, "urlopen", fail_urlopen):
        with patched(request_module.request, "build_opener", lambda *_handlers: FakeOpener()):
            result = request_module.safe_urlopen(
                "https://images.example/v1",
                5,
                policy="api",
            )

    assert result is response
    assert calls == [("https://images.example/v1", 5)]


def test_read_response_bytes_wraps_timeout_error():
    _mod, request_module = load_request_module()
    response = FakeResponse(read_exc=TimeoutError("The read operation timed out"))

    try:
        request_module.read_response_bytes(response)
    except request_module.NetworkOperationError as exc:
        assert exc.error_data["code"] == "timeout"
        assert "timed out" in exc.error_data["message"].lower()
    else:
        raise AssertionError("Expected NetworkOperationError")


def test_read_response_bytes_rejects_oversized_response():
    _mod, request_module = load_request_module()
    response = FakeResponse(body=b"x" * 17)

    try:
        request_module.read_response_bytes(response, max_bytes=16)
    except request_module.NetworkOperationError as exc:
        assert exc.error_data["code"] == "response_too_large"
        assert exc.error_data["category"] == "validation_error"
    else:
        raise AssertionError("Expected oversized response rejection")


def test_request_json_returns_http_error_payload_from_response_body():
    mod, request_module = load_request_module()

    def fake_urlopen(*_args, **_kwargs):
        raise error.HTTPError(
            url="https://images.example/v1/responses",
            code=429,
            msg="Too Many Requests",
            hdrs={"x-request-id": "req-rate"},
            fp=io.BytesIO(b'{"error":{"code":"rate_limited","message":"Slow down"}}'),
        )

    with patched(
        request_module.request,
        "build_opener",
        lambda *_handlers: FakeOpener(fake_urlopen),
    ):
        result = request_module.request_json(
            "https://images.example/v1/responses",
            {"Authorization": "Bearer test"},
            {"model": "response-model-v1", "input": []},
            5,
            mod.ApiResult,
        )

    assert result.ok is False
    assert result.status == 429
    assert result.error["code"] == "rate_limited"
    assert result.error["message"] == "Slow down"
    assert result.request_id == "req-rate"


def test_request_json_sets_explicit_user_agent():
    mod, request_module = load_request_module()
    captured = {}

    def fake_urlopen(target, *_args, **_kwargs):
        captured["user_agent"] = target.get_header("User-agent")
        return FakeResponse(body=b"{}", status=200)

    with patched(request_module, "safe_urlopen", fake_urlopen):
        request_module.request_json(
            "https://images.example/v1/images/generations",
            {"Authorization": "Bearer test"},
            {"model": "image-model-v1", "prompt": "test"},
            5,
            mod.ApiResult,
        )

    assert captured["user_agent"] == "Henry-Image/1.0.1"


def test_request_multipart_returns_network_timeout_payload():
    mod, request_module = load_request_module()

    def fake_urlopen(*_args, **_kwargs):
        raise error.URLError(TimeoutError("The read operation timed out"))

    with patched(
        request_module.request,
        "build_opener",
        lambda *_handlers: FakeOpener(fake_urlopen),
    ):
        result = request_module.request_multipart(
            "https://images.example/v1/images/edits",
            {"Authorization": "Bearer test"},
            {"model": "image-model-v1", "prompt": "test"},
            [],
            5,
            mod.ApiResult,
        )

    assert result.ok is False
    assert result.status is None
    assert result.error["code"] == "timeout"
    assert "timed out" in result.error["message"].lower()


@pytest.mark.parametrize("request_name", ["request_json", "request_multipart"])
def test_request_entrypoints_return_structured_error_for_oversized_success_response(request_name):
    mod, request_module = load_request_module()
    response = FakeResponse(
        body=b"x" * (request_module.MAX_API_RESPONSE_BYTES + 1),
        status=200,
        headers={"x-request-id": "req-too-large"},
    )

    with patched(request_module, "safe_urlopen", lambda *_args, **_kwargs: response):
        if request_name == "request_json":
            result = request_module.request_json(
                "https://images.example/v1/responses",
                {"Authorization": "Bearer test"},
                {"model": "response-model-v1", "input": []},
                5,
                mod.ApiResult,
            )
        else:
            result = request_module.request_multipart(
                "https://images.example/v1/images/edits",
                {"Authorization": "Bearer test"},
                {"model": "image-model-v1", "prompt": "test"},
                [],
                5,
                mod.ApiResult,
            )

    assert result.ok is False
    assert result.status == 200
    assert result.error["code"] == "response_too_large"
    assert result.error["category"] == "validation_error"
    assert result.request_id == "req-too-large"


def test_classify_api_failure_boundaries():
    _mod, request_module = load_request_module()

    assert request_module.classify_api_failure({"message": "Missing API key"}) == "missing_credentials"
    assert request_module.classify_api_failure({"status": 429, "message": "Rate limit"}) == "rate_limited"
    assert request_module.classify_api_failure({"message": "The read operation timed out"}) == "timeout"
    assert request_module.classify_api_failure({"code": "url_error", "message": "connection reset"}) == "network_error"
    assert request_module.classify_api_failure({"status": 404, "message": "Not Found"}) == "not_found"
    assert request_module.classify_api_failure({"status": 400, "message": "Bad request"}) == "bad_parameter"
    assert request_module.classify_api_failure({"status": 503, "message": "Server unavailable"}) == "server_error"


def test_api_redirect_handler_preserves_auth_only_for_same_origin():
    _mod, request_module = load_request_module()
    handler = request_module.SafeRedirectHandler("api")
    original = request.Request(
        "https://images.example/v1/responses",
        data=b"{}",
        headers={"Authorization": "Bearer test"},
        method="POST",
    )

    redirected = handler.redirect_request(
        original,
        None,
        307,
        "Temporary Redirect",
        {"Location": "https://images.example/v2/responses"},
        "https://images.example/v2/responses",
    )

    assert redirected.full_url == "https://images.example/v2/responses"
    assert redirected.get_header("Authorization") == "Bearer test"


def test_api_redirect_handler_rejects_cross_origin_auth_redirect():
    _mod, request_module = load_request_module()
    handler = request_module.SafeRedirectHandler("api")
    original = request.Request(
        "https://images.example/v1/responses",
        data=b"{}",
        headers={"Authorization": "Bearer test"},
        method="POST",
    )

    try:
        handler.redirect_request(
            original,
            None,
            307,
            "Temporary Redirect",
            {"Location": "https://other.example/capture"},
            "https://other.example/capture",
        )
    except request_module.NetworkOperationError as exc:
        assert exc.error_data["code"] == "unsafe_redirect"
        assert exc.error_data["category"] == "validation_error"
    else:
        raise AssertionError("Expected unsafe cross-origin redirect rejection")


def test_api_redirect_handler_rejects_malformed_redirect_url():
    _mod, request_module = load_request_module()
    handler = request_module.SafeRedirectHandler("api")
    original = request.Request(
        "https://images.example/v1/responses",
        data=b"{}",
        headers={"Authorization": "Bearer test"},
        method="POST",
    )

    try:
        handler.redirect_request(
            original,
            None,
            307,
            "Temporary Redirect",
            {"Location": "https://[broken"},
            "https://[broken",
        )
    except request_module.NetworkOperationError as exc:
        assert exc.error_data["code"] == "unsafe_redirect"
        assert exc.error_data["category"] == "validation_error"
    else:
        raise AssertionError("Expected malformed API redirect rejection")


def test_image_redirect_handler_allows_https_cdn_but_rejects_downgrade():
    _mod, request_module = load_request_module()
    handler = request_module.SafeRedirectHandler("image")
    original = request.Request(
        "https://images.example/result.png",
        headers={"Authorization": "Bearer must-not-leak"},
    )

    with patched(
        request_module,
        "resolve_public_image_url",
        lambda _url: ("cdn.example", 443, "93.184.216.34"),
    ):
        redirected = handler.redirect_request(
            original,
            None,
            302,
            "Found",
            {"Location": "https://cdn.example/result.png"},
            "https://cdn.example/result.png",
        )
    assert redirected.full_url == "https://cdn.example/result.png"
    assert redirected.get_header("Authorization") is None

    try:
        handler.redirect_request(
            original,
            None,
            302,
            "Found",
            {"Location": "http://cdn.example/result.png"},
            "http://cdn.example/result.png",
        )
    except request_module.NetworkOperationError as exc:
        assert exc.error_data["code"] == "unsafe_image_url"
    else:
        raise AssertionError("Expected HTTPS downgrade rejection")


def test_image_redirect_handler_rejects_malformed_http_port():
    _mod, request_module = load_request_module()
    handler = request_module.SafeRedirectHandler("image")
    original = request.Request("https://images.example/result.png")

    try:
        handler.redirect_request(
            original,
            None,
            302,
            "Found",
            {"Location": "https://cdn.example:bad/result.png"},
            "https://cdn.example:bad/result.png",
        )
    except request_module.NetworkOperationError as exc:
        assert exc.error_data["code"] == "unsafe_image_url"
    else:
        raise AssertionError("Expected malformed image redirect rejection")


def test_image_redirect_handler_rejects_malformed_ipv6_url():
    _mod, request_module = load_request_module()
    handler = request_module.SafeRedirectHandler("image")
    original = request.Request("https://images.example/result.png")

    try:
        handler.redirect_request(
            original,
            None,
            302,
            "Found",
            {"Location": "https://[broken"},
            "https://[broken",
        )
    except request_module.NetworkOperationError as exc:
        assert exc.error_data["code"] == "unsafe_image_url"
        assert exc.error_data["category"] == "validation_error"
    else:
        raise AssertionError("Expected malformed image redirect rejection")


def test_download_image_rejects_non_http_url():
    _mod, request_module = load_request_module()

    try:
        request_module.download_image(
            "file:///tmp/private.png",
            5,
            is_data_image_url=lambda _value: False,
        )
    except request_module.NetworkOperationError as exc:
        assert exc.error_data["code"] == "unsafe_image_url"
        assert exc.error_data["category"] == "validation_error"
    else:
        raise AssertionError("Expected non-HTTP image URL rejection")


def test_download_image_rejects_malformed_http_port():
    _mod, request_module = load_request_module()

    try:
        request_module.download_image(
            "https://images.example:bad/result.png",
            5,
            is_data_image_url=lambda _value: False,
        )
    except request_module.NetworkOperationError as exc:
        assert exc.error_data["code"] == "unsafe_image_url"
        assert exc.error_data["category"] == "validation_error"
    else:
        raise AssertionError("Expected malformed HTTP image URL rejection")


@pytest.mark.parametrize(
    "url",
    (
        "http://127.0.0.1/result.png",
        "http://10.0.0.7/result.png",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/result.png",
        "http://[fc00::7]/result.png",
    ),
)
def test_download_image_rejects_non_public_literal_addresses_before_open(url):
    _mod, request_module = load_request_module()

    def fail_open(*_args, **_kwargs):
        raise AssertionError("Unsafe image address must be rejected before opening a connection")

    with patched(request_module, "safe_urlopen", fail_open):
        try:
            request_module.download_image(url, 5, is_data_image_url=lambda _value: False)
        except request_module.NetworkOperationError as exc:
            assert exc.error_data["code"] == "unsafe_image_url"
            assert exc.error_data["category"] == "validation_error"
        else:
            raise AssertionError("Expected non-public image address rejection")


def test_download_image_rejects_private_dns_answers_before_open():
    _mod, request_module = load_request_module()

    def fake_getaddrinfo(*_args, **_kwargs):
        return [(request_module.socket.AF_INET, request_module.socket.SOCK_STREAM, 6, "", ("10.0.0.7", 443))]

    def fail_open(*_args, **_kwargs):
        raise AssertionError("Private DNS answer must be rejected before opening a connection")

    with patched(request_module.socket, "getaddrinfo", fake_getaddrinfo):
        with patched(request_module, "safe_urlopen", fail_open):
            try:
                request_module.download_image(
                    "https://cdn.example/result.png",
                    5,
                    is_data_image_url=lambda _value: False,
                )
            except request_module.NetworkOperationError as exc:
                assert exc.error_data["code"] == "unsafe_image_url"
            else:
                raise AssertionError("Expected private DNS answer rejection")


def test_download_image_rejects_mixed_public_and_private_dns_answers():
    _mod, request_module = load_request_module()

    def fake_getaddrinfo(*_args, **_kwargs):
        return [
            (request_module.socket.AF_INET, request_module.socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (request_module.socket.AF_INET, request_module.socket.SOCK_STREAM, 6, "", ("10.0.0.7", 443)),
        ]

    with patched(request_module.socket, "getaddrinfo", fake_getaddrinfo):
        try:
            request_module.resolve_public_image_url("https://cdn.example/result.png")
        except request_module.NetworkOperationError as exc:
            assert exc.error_data["code"] == "unsafe_image_url"
        else:
            raise AssertionError("Expected mixed DNS answer rejection")


def test_image_redirect_rejects_private_dns_target():
    _mod, request_module = load_request_module()
    handler = request_module.SafeRedirectHandler("image")
    original = request.Request("https://images.example/result.png")

    def fake_getaddrinfo(*_args, **_kwargs):
        return [(request_module.socket.AF_INET, request_module.socket.SOCK_STREAM, 6, "", ("10.0.0.7", 443))]

    with patched(request_module.socket, "getaddrinfo", fake_getaddrinfo):
        try:
            handler.redirect_request(
                original,
                None,
                302,
                "Found",
                {"Location": "https://cdn.example/result.png"},
                "https://cdn.example/result.png",
            )
        except request_module.NetworkOperationError as exc:
            assert exc.error_data["code"] == "unsafe_image_url"
        else:
            raise AssertionError("Expected private redirect target rejection")


def test_validated_image_connection_uses_selected_ip_without_dns_lookup():
    _mod, request_module = load_request_module()
    calls = {}

    class FakeSocket:
        def settimeout(self, timeout):
            calls["timeout"] = timeout

        def setsockopt(self, level, option, value):
            calls["socketopt"] = (level, option, value)

        def connect(self, address):
            calls["address"] = address

        def close(self):
            calls["closed"] = True

    def fake_socket(family, socket_type):
        calls["family"] = family
        calls["socket_type"] = socket_type
        return FakeSocket()

    with patched(request_module.socket, "socket", fake_socket):
        connection = request_module.ValidatedImageHTTPConnection(
            "cdn.example",
            443,
            connect_host="93.184.216.34",
            timeout=5,
        )
        connection.connect()

    assert connection.host == "cdn.example"
    assert calls["address"] == ("93.184.216.34", 443)


def test_validated_https_connection_keeps_hostname_for_sni_and_host_header():
    _mod, request_module = load_request_module()
    calls = {}

    class FakeSocket:
        def settimeout(self, timeout):
            calls["timeout"] = timeout

        def setsockopt(self, level, option, value):
            calls["socketopt"] = (level, option, value)

        def connect(self, address):
            calls["address"] = address

        def close(self):
            calls["closed"] = True

    class FakeTLSSocket:
        def __init__(self):
            self.written = []

        def sendall(self, data):
            self.written.append(data)

    tls_socket = FakeTLSSocket()
    raw_socket = FakeSocket()

    class FakeTLSContext:
        def wrap_socket(self, sock, *, server_hostname):
            calls["tcp_socket"] = sock
            calls["server_hostname"] = server_hostname
            return tls_socket

    def fake_socket(*_args):
        calls["raw_socket"] = raw_socket
        return raw_socket

    with patched(request_module.socket, "socket", fake_socket):
        connection = request_module.ValidatedImageHTTPSConnection(
            "cdn.example",
            443,
            connect_host="93.184.216.34",
            context=FakeTLSContext(),
            timeout=5,
        )
        connection.connect()
        assert connection.sock is tls_socket
        connection.putrequest("GET", "/result.png")
        connection.endheaders()

    assert calls["address"] == ("93.184.216.34", 443)
    assert calls["raw_socket"] is raw_socket
    assert calls["tcp_socket"] is raw_socket
    assert calls["server_hostname"] == "cdn.example"
    request_bytes = b"".join(tls_socket.written)
    assert b"Host: cdn.example\r\n" in request_bytes
    assert b"93.184.216.34" not in request_bytes


def test_request_json_returns_structured_error_for_invalid_json_body():
    mod, request_module = load_request_module()
    response = FakeResponse(
        body=b"not-json",
        status=200,
        headers={"x-request-id": "req-invalid-json"},
    )

    with patched(request_module, "safe_urlopen", lambda *_args, **_kwargs: response):
        result = request_module.request_json(
            "https://images.example/v1/responses",
            {"Authorization": "Bearer test"},
            {"model": "response-model-v1"},
            5,
            mod.ApiResult,
        )

    assert result.ok is False
    assert result.status == 200
    assert result.request_id == "req-invalid-json"
    assert result.error["code"] == "invalid_response_data"
    assert result.error["category"] == "validation_error"


def test_request_json_returns_structured_error_for_non_object_json_body():
    mod, request_module = load_request_module()
    response = FakeResponse(
        body=json.dumps([{"unexpected": True}]).encode("utf-8"),
        status=200,
        headers={"x-request-id": "req-invalid-shape"},
    )

    with patched(request_module, "safe_urlopen", lambda *_args, **_kwargs: response):
        result = request_module.request_json(
            "https://images.example/v1/responses",
            {"Authorization": "Bearer test"},
            {"model": "response-model-v1"},
            5,
            mod.ApiResult,
        )

    assert result.ok is False
    assert result.status == 200
    assert result.request_id == "req-invalid-shape"
    assert result.error["code"] == "invalid_response_data"
    assert result.error["category"] == "validation_error"


def test_write_output_bundle_rolls_back_when_manifest_conflicts():
    _mod, request_module = load_request_module()
    png = b"\x89PNG\r\n\x1a\nimage"

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "result.png"
        manifest = Path(str(out) + ".json")
        manifest.write_text("OLD", encoding="utf-8")

        try:
            request_module.write_output_bundle(
                [png],
                str(out),
                "png",
                False,
                manifest_factory=lambda outputs: {"outputs": outputs},
                redact=lambda value: value,
            )
        except ValueError as exc:
            assert "manifest already exists" in str(exc).lower()
        else:
            raise AssertionError("Expected manifest conflict")

        assert not out.exists()
        assert manifest.read_text(encoding="utf-8") == "OLD"


def test_write_output_bundle_supports_file_output_without_extension():
    _mod, request_module = load_request_module()
    png = b"\x89PNG\r\n\x1a\nimage"

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        out = root / "result"

        outputs, manifest_path = request_module.write_output_bundle(
            [png],
            str(out),
            "png",
            False,
            manifest_factory=lambda bundle_outputs: {"outputs": bundle_outputs},
            redact=lambda value: value,
        )

        assert out.read_bytes() == png
        assert Path(manifest_path) == root / "result.json"
        assert Path(manifest_path).is_file()
        assert outputs[0]["path"] == str(out)


def test_write_output_bundle_restores_existing_files_when_commit_fails():
    _mod, request_module = load_request_module()
    old_png = b"\x89PNG\r\n\x1a\nold"
    new_png = b"\x89PNG\r\n\x1a\nnew"

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "result.png"
        manifest = Path(str(out) + ".json")
        out.write_bytes(old_png)
        manifest.write_text("OLD", encoding="utf-8")
        real_replace = request_module.os.replace
        commit_count = 0

        def fail_manifest_commit(source, destination):
            nonlocal commit_count
            if ".tmp-" in str(source):
                commit_count += 1
                if commit_count == 2:
                    raise OSError("simulated manifest commit failure")
            return real_replace(source, destination)

        with patched(request_module.os, "replace", fail_manifest_commit):
            try:
                request_module.write_output_bundle(
                    [new_png],
                    str(out),
                    "png",
                    True,
                    manifest_factory=lambda outputs: {"outputs": outputs},
                    redact=lambda value: value,
                )
            except OSError as exc:
                assert "simulated manifest commit failure" in str(exc)
            else:
                raise AssertionError("Expected simulated commit failure")

        assert out.read_bytes() == old_png
        assert manifest.read_text(encoding="utf-8") == "OLD"
        assert not list(Path(tmp).glob("*.tmp-*"))
        assert not list(Path(tmp).glob("*.bak-*"))


def test_write_output_bundle_rolls_back_all_images_when_multi_image_commit_fails():
    _mod, request_module = load_request_module()
    old_first = b"\x89PNG\r\n\x1a\nold-first"
    old_second = b"\x89PNG\r\n\x1a\nold-second"
    new_first = b"\x89PNG\r\n\x1a\nnew-first"
    new_second = b"\x89PNG\r\n\x1a\nnew-second"

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        out = root / "result.png"
        first = root / "result-1.png"
        second = root / "result-2.png"
        manifest = Path(str(out) + ".json")
        first.write_bytes(old_first)
        second.write_bytes(old_second)
        manifest.write_text("OLD", encoding="utf-8")
        real_replace = request_module.os.replace
        commit_count = 0

        def fail_second_image_commit(source, destination):
            nonlocal commit_count
            if ".tmp-" in str(source):
                commit_count += 1
                if commit_count == 2:
                    raise OSError("simulated second image commit failure")
            return real_replace(source, destination)

        with patched(request_module.os, "replace", fail_second_image_commit):
            try:
                request_module.write_output_bundle(
                    [new_first, new_second],
                    str(out),
                    "png",
                    True,
                    manifest_factory=lambda outputs: {"outputs": outputs},
                    redact=lambda value: value,
                )
            except OSError as exc:
                assert "simulated second image commit failure" in str(exc)
            else:
                raise AssertionError("Expected simulated multi-image commit failure")

        assert first.read_bytes() == old_first
        assert second.read_bytes() == old_second
        assert manifest.read_text(encoding="utf-8") == "OLD"
        assert not list(root.glob("*.tmp-*"))
        assert not list(root.glob("*.bak-*"))


def test_write_output_bundle_preserves_backup_when_restore_itself_fails():
    _mod, request_module = load_request_module()
    old_png = b"\x89PNG\r\n\x1a\nold"
    new_png = b"\x89PNG\r\n\x1a\nnew"

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        out = root / "result.png"
        manifest = Path(str(out) + ".json")
        out.write_bytes(old_png)
        manifest.write_text("OLD", encoding="utf-8")
        real_replace = request_module.os.replace

        def fail_commit_and_image_restore(source, destination):
            if ".tmp-" in str(source) and Path(destination) == manifest:
                raise OSError("simulated manifest commit failure")
            if ".bak-" in str(source) and Path(destination) == out:
                raise OSError("simulated image restore failure")
            return real_replace(source, destination)

        with patched(request_module.os, "replace", fail_commit_and_image_restore):
            try:
                request_module.write_output_bundle(
                    [new_png],
                    str(out),
                    "png",
                    True,
                    manifest_factory=lambda outputs: {"outputs": outputs},
                    redact=lambda value: value,
                )
            except OSError as exc:
                assert "simulated manifest commit failure" in str(exc)
                assert "simulated image restore failure" in str(exc)
                assert ".bak-" in str(exc)
            else:
                raise AssertionError("Expected simulated commit failure")

        backups = list(root.glob("result.png.bak-*"))
        assert len(backups) == 1
        assert backups[0].read_bytes() == old_png
        assert manifest.read_text(encoding="utf-8") == "OLD"


def test_write_output_bundle_rejects_directory_targets_without_backups():
    _mod, request_module = load_request_module()
    png = b"\x89PNG\r\n\x1a\nimage"

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        out = root / "result.png"
        manifest = Path(str(out) + ".json")
        manifest.mkdir()
        marker = manifest / "keep.txt"
        marker.write_text("KEEP", encoding="utf-8")

        try:
            request_module.write_output_bundle(
                [png],
                str(out),
                "png",
                True,
                manifest_factory=lambda outputs: {"outputs": outputs},
                redact=lambda value: value,
            )
        except ValueError as exc:
            assert "regular file" in str(exc).lower()
        else:
            raise AssertionError("Expected directory target rejection")

        assert marker.read_text(encoding="utf-8") == "KEEP"
        assert not out.exists()
        assert not list(root.glob("*.tmp-*"))
        assert not list(root.glob("*.bak-*"))


def test_validate_output_target_rejects_dangling_symlink():
    _mod, request_module = load_request_module()

    class DanglingSymlink:
        def is_symlink(self):
            return True

        def exists(self):
            return False

        def is_file(self):
            return False

        def __str__(self):
            return "dangling.png"

    try:
        request_module.validate_output_target(DanglingSymlink())
    except ValueError as exc:
        assert "regular file" in str(exc).lower()
    else:
        raise AssertionError("Expected dangling symlink rejection")
