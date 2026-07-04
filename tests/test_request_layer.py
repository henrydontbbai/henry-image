import io
import sys
from urllib import error

from helpers import load_module, patched


class FakeResponse:
    def __init__(self, *, body=b"", read_exc=None, status=200, headers=None):
        self._body = body
        self._read_exc = read_exc
        self.status = status
        self.headers = headers or {}

    def read(self):
        if self._read_exc is not None:
            raise self._read_exc
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


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

    with patched(request_module.request, "urlopen", fake_urlopen):
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


def test_request_multipart_returns_network_timeout_payload():
    mod, request_module = load_request_module()

    def fake_urlopen(*_args, **_kwargs):
        raise error.URLError(TimeoutError("The read operation timed out"))

    with patched(request_module.request, "urlopen", fake_urlopen):
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


def test_classify_api_failure_boundaries():
    _mod, request_module = load_request_module()

    assert request_module.classify_api_failure({"message": "Missing API key"}) == "missing_credentials"
    assert request_module.classify_api_failure({"status": 429, "message": "Rate limit"}) == "rate_limited"
    assert request_module.classify_api_failure({"message": "The read operation timed out"}) == "timeout"
    assert request_module.classify_api_failure({"code": "url_error", "message": "connection reset"}) == "network_error"
    assert request_module.classify_api_failure({"status": 404, "message": "Not Found"}) == "not_found"
    assert request_module.classify_api_failure({"status": 400, "message": "Bad request"}) == "bad_parameter"
    assert request_module.classify_api_failure({"status": 503, "message": "Server unavailable"}) == "server_error"
