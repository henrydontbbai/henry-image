from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
CHECKED_PATHS = (
    ROOT / "README.md",
    ROOT / "CHANGELOG.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "SECURITY.md",
    ROOT / "SKILL.md",
    ROOT / ".gitattributes",
    ROOT / ".gitignore",
    ROOT / ".github",
    ROOT / "agents",
    ROOT / "docs",
    ROOT / "references",
    ROOT / "scripts",
    ROOT / "tests",
)
TEXT_SUFFIXES = {".md", ".py", ".yaml", ".yml", ".json", ".txt"}
CURRENT_FILE = Path(__file__).resolve()
def marker(*parts):
    return "".join(parts)


DISALLOWED_TEXT_MARKERS = (
    marker("Open", "AI"),
    marker("Ai", "MaMi"),
    marker("Cod", "ex"),
    marker("Azu", "re"),
    marker("AO", "AI"),
    marker("Open ", "WebUI"),
    marker("Fl", "ux"),
    marker("Mid", "journey"),
    marker("SD", "XL"),
    marker("Open", "SCAD"),
    marker("gpt", "-image-2"),
    marker("gpt", "-5"),
    marker("probe-image-", "providers"),
    marker("provider-", "cache"),
    marker("candidate-", "policy"),
    marker("agents/", "open", "ai.yaml"),
    marker("HENRY_IMAGE_", "OPEN", "AI_API_KEY"),
    marker("HENRY_IMAGE_", "ACCESS", "_KEY"),
    marker("HENRY_IMAGE_", "API_", "BASE"),
    marker("HENRY_IMAGE_", "API_", "BASE_URL"),
    marker("HENRY_IMAGE_", "RESPONSE", "_MODEL"),
    marker("HENRY_IMAGE_", "MODEL", "_IMAGE"),
    marker("OPEN", "AI_"),
    marker("AZ", "URE_"),
    marker("AO", "AI_"),
    marker("AIM", "AMI_"),
    marker("CODE", "X_"),
    marker("OPEN", "AI_COMP", "AT_"),
    marker("GPT_", "IMAGE_"),
)


def iter_text_files():
    for path in CHECKED_PATHS:
        if path.is_file():
            if path.resolve() != CURRENT_FILE:
                yield path
            continue
        for candidate in path.rglob("*"):
            if candidate.resolve() == CURRENT_FILE:
                continue
            if candidate.is_file() and candidate.suffix.lower() in TEXT_SUFFIXES:
                yield candidate


def workflow_job_block(workflow_text: str, job_name: str) -> str:
    pattern = re.compile(
        rf"(?ms)^  {re.escape(job_name)}:\n.*?(?=^  [A-Za-z0-9_-]+:\n|\Z)"
    )
    match = pattern.search(workflow_text)
    assert match, f"missing workflow job block: {job_name}"
    return match.group(0)


def test_public_release_files_exist():
    expected = (
        ROOT / "README.md",
        ROOT / "CHANGELOG.md",
        ROOT / "LICENSE",
        ROOT / "CONTRIBUTING.md",
        ROOT / "SECURITY.md",
        ROOT / ".env.example",
        ROOT / "SKILL.md",
        ROOT / "docs" / "release-process.md",
        ROOT / "agents" / "henry-image.yaml",
        ROOT / ".github" / "workflows" / "ci.yml",
        ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.md",
        ROOT / ".github" / "ISSUE_TEMPLATE" / "feature_request.md",
        ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md",
    )
    missing = [str(path.relative_to(ROOT)) for path in expected if not path.exists()]
    assert not missing, "\n".join(missing)


def test_env_example_only_exposes_canonical_public_variables():
    env_example = ROOT / ".env.example"
    text = env_example.read_text(encoding="utf-8")
    keys = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" in stripped:
            keys.append(stripped.split("=", 1)[0].strip())

    assert keys == [
        "HENRY_IMAGE_BASE_URL",
        "HENRY_IMAGE_API_KEY",
        "HENRY_IMAGE_MODEL",
        "HENRY_IMAGE_IMAGE_MODEL",
    ]


def test_readme_includes_minimal_quickstart_and_troubleshooting():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    for expected in (
        "## Quick Start",
        "## First Run",
        "## Batch",
        "## Job Recovery",
        "## Images Route Options",
        "`--images-response-format`",
        "`--output-compression`",
        "## Output Contract",
        "## Troubleshooting",
        "workflow_profile",
        "docs/release-process.md",
        ".env.example",
        "python -m pytest -q",
        "python .\\scripts\\henry_image.py generate",
        "python .\\scripts\\henry_image.py quick_validate",
    ):
        assert expected in text


def test_public_version_markers_are_in_sync():
    version_text = (ROOT / "scripts" / "henry_image_core" / "version.py").read_text(encoding="utf-8")
    request_text = (ROOT / "scripts" / "henry_image_core" / "request.py").read_text(encoding="utf-8")
    readme_text = (ROOT / "README.md").read_text(encoding="utf-8")
    skill_text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    changelog_text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    security_text = (ROOT / "SECURITY.md").read_text(encoding="utf-8")

    version_match = re.search(r'HENRY_IMAGE_VERSION = "([^"]+)"', version_text)
    assert version_match
    version = version_match.group(1)

    assert "from henry_image_core.version import API_USER_AGENT" in request_text
    assert "Henry-Image/1.0.1" not in request_text
    assert f"Version: `{version}`" in readme_text
    assert f"V{version}" in skill_text
    assert f"## {version} -" in changelog_text
    major, minor, _patch = version.split(".", 2)
    assert f"latest published `{major}.{minor}.x` patch" in security_text


def test_ci_workflow_has_layered_jobs_and_python_matrix():
    text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    for expected in (
        "smoke:",
        "hygiene:",
        "contract:",
        "test:",
        "matrix:",
        'python-version: ["3.9", "3.10", "3.11", "3.12"]',
        "python ./scripts/henry_image.py --help",
        "python ./scripts/henry_image.py generate --help",
        "python ./scripts/henry_image.py quick_validate",
        "python -m pytest -q tests/test_repo_hygiene.py",
        "python -m pytest -q tests/test_contract.py tests/test_jobs.py tests/test_request_layer.py tests/test_workflow_profile.py",
        "python -m pytest -q",
    ):
        assert expected in text

    smoke = workflow_job_block(text, "smoke")
    hygiene = workflow_job_block(text, "hygiene")
    contract = workflow_job_block(text, "contract")
    test = workflow_job_block(text, "test")

    assert "runs-on: ubuntu-latest" in smoke
    assert "python ./scripts/henry_image.py --help" in smoke
    assert "python ./scripts/henry_image.py generate --help" in smoke
    assert "python ./scripts/henry_image.py quick_validate" in smoke

    assert "runs-on: ubuntu-latest" in hygiene
    assert "python -m pytest -q tests/test_repo_hygiene.py" in hygiene

    assert "runs-on: ubuntu-latest" in contract
    assert (
        "python -m pytest -q tests/test_contract.py tests/test_jobs.py "
        "tests/test_request_layer.py tests/test_workflow_profile.py"
    ) in contract

    assert "runs-on: ubuntu-latest" in test
    assert "matrix:" in test
    assert 'python-version: ["3.9", "3.10", "3.11", "3.12"]' in test
    assert "python -m pytest -q" in test


def test_ci_workflow_includes_windows_runtime_coverage():
    text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    block = workflow_job_block(text, "windows")

    for expected in (
        "runs-on: windows-latest",
        'python-version: ["3.9", "3.10", "3.12"]',
        "matrix:",
        "python .\\scripts\\henry_image.py quick_validate",
        "python -m pytest -q",
    ):
        assert expected in block


def test_ci_workflow_includes_ubuntu_runtime_coverage():
    text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    for job_name in ("smoke", "hygiene", "contract", "test"):
        block = workflow_job_block(text, job_name)
        assert "runs-on: ubuntu-latest" in block


def test_ci_workflow_includes_macos_runtime_coverage():
    text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    block = workflow_job_block(text, "macos")

    for expected in (
        "runs-on: macos-latest",
        "matrix:",
        'python-version: ["3.9", "3.10"]',
        "python-version: ${{ matrix.python-version }}",
        "python -m pytest -q",
        "python ./scripts/henry_image.py quick_validate",
    ):
        assert expected in block


def test_ci_workflow_covers_python_310_on_all_supported_platforms():
    text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    expected_matrices = {
        "test": 'python-version: ["3.9", "3.10", "3.11", "3.12"]',
        "windows": 'python-version: ["3.9", "3.10", "3.12"]',
        "macos": 'python-version: ["3.9", "3.10"]',
    }

    for job_name, expected_matrix in expected_matrices.items():
        assert expected_matrix in workflow_job_block(text, job_name)


def test_api_notes_define_stable_contract_and_workflow_profile_boundary():
    text = (ROOT / "references" / "api.md").read_text(encoding="utf-8")
    for expected in (
        "## Stable stdout contract",
        "`ok`",
        "`metadata`",
        "## Stable metadata fields",
        "when present",
        "`workflow_profile`",
        "diagnostic",
        "## Active advanced images options",
        "`--images-response-format`",
        "`--output-compression`",
        "## Batch JSONL example",
        "## Manifest example",
        "## Failure example",
    ):
        assert expected in text


def test_api_notes_document_reliability_statuses_and_error_codes():
    text = (ROOT / "references" / "api.md").read_text(encoding="utf-8")
    for expected in (
        "## Reliability statuses and error codes",
        "`identity_unverified`",
        "`cancel_pending`",
        "`cancel_failed`",
        "`unsafe_redirect`",
        "`unsafe_image_url`",
        "`invalid_response_data`",
        "`unsupported_output_count`",
        "`invalid_image_format`",
        "`incompatible_flags`",
        "`output_write_failed`",
        "`invalid_job_metadata`",
        "`cleanup_failed`",
        "`response_too_large`",
        "`job_start_failed`",
    ):
        assert expected in text


def test_maintainer_docs_cover_local_checks_and_private_reporting():
    contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    for expected in (
        "# Contributing",
        "python -m pytest -q",
        "python .\\scripts\\henry_image.py quick_validate",
        "CHANGELOG.md",
    ):
        assert expected in contributing
    for expected in (
        "# Security Policy",
        "Report security issues privately.",
        "GitHub Private Vulnerability Reporting",
        "https://github.com/henrydontbbai/henry-image/security/advisories/new",
        "Please avoid filing public issues",
        "## Supported Versions",
    ):
        assert expected in security


def test_release_process_doc_defines_version_rules_and_tag_policy():
    text = (ROOT / "docs" / "release-process.md").read_text(encoding="utf-8")
    for expected in (
        "# Release Process",
        "Patch",
        "Minor",
        "Major",
        "test-only",
        "CI-only",
        "docs-only",
        "vX.Y.Z",
        "python -m pytest -q",
        "python .\\scripts\\henry_image.py quick_validate",
        "OpenCode",
        "Ubuntu",
        "Windows",
        "macOS",
        "scripts/henry_image_core/version.py",
        "transport",
        "does not block",
        "git tag",
        "GitHub Release",
        "optional",
    ):
        assert expected in text


def test_committed_text_files_do_not_embed_disallowed_external_names():
    offenders = []
    for path in iter_text_files():
        text = path.read_text(encoding="utf-8")
        for marker in DISALLOWED_TEXT_MARKERS:
            if marker in text:
                offenders.append(f"{path.relative_to(ROOT)} contains {marker}")

    assert not offenders, "\n".join(offenders)
