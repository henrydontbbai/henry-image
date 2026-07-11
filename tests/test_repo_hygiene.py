from copy import deepcopy
from pathlib import Path
import re

import pytest
import yaml

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

WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ci.yml"
EXPECTED_WORKFLOW_RUNNERS = {
    "smoke": "ubuntu-latest",
    "hygiene": "ubuntu-latest",
    "contract": "ubuntu-latest",
    "test": "ubuntu-latest",
    "windows": "windows-latest",
    "macos": "macos-latest",
}
EXPECTED_WORKFLOW_MATRICES = {
    "test": {"3.9", "3.10", "3.11", "3.12"},
    "windows": {"3.9", "3.10", "3.12"},
    "macos": {"3.9", "3.10"},
}
EXPECTED_WORKFLOW_COMMANDS = {
    "smoke": {
        "python ./scripts/henry_image.py --help",
        "python ./scripts/henry_image.py generate --help",
        "python ./scripts/henry_image.py quick_validate",
    },
    "hygiene": {"python -m pytest -q tests/test_repo_hygiene.py"},
    "contract": {
        "python -m pytest -q tests/test_contract.py tests/test_jobs.py "
        "tests/test_request_layer.py tests/test_workflow_profile.py"
    },
    "test": {"python -m pytest -q"},
    "windows": {"python -m pytest -q", "python .\\scripts\\henry_image.py quick_validate"},
    "macos": {"python -m pytest -q", "python ./scripts/henry_image.py quick_validate"},
}
PYTEST_WORKFLOW_JOBS = {"hygiene", "contract", "test", "windows", "macos"}


def load_workflow_text(text: str) -> dict:
    workflow = yaml.load(text, Loader=yaml.BaseLoader)
    assert isinstance(workflow, dict)
    return workflow


def load_ci_workflow() -> dict:
    return load_workflow_text(WORKFLOW_PATH.read_text(encoding="utf-8"))


def workflow_contract_issues(workflow: object) -> list[str]:
    if not isinstance(workflow, dict):
        return ["workflow must be a mapping"]

    issues: list[str] = []
    triggers = workflow.get("on")
    if not isinstance(triggers, dict) or not {"push", "pull_request"}.issubset(triggers):
        issues.append("workflow must define push and pull_request triggers")

    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict):
        return issues + ["workflow must define jobs as a mapping"]

    for job_name, expected_runner in EXPECTED_WORKFLOW_RUNNERS.items():
        job = jobs.get(job_name)
        if not isinstance(job, dict):
            issues.append(f"workflow is missing required job: {job_name}")
            continue

        if job.get("runs-on") != expected_runner:
            issues.append(f"{job_name} must run on {expected_runner}")

        steps = job.get("steps")
        if not isinstance(steps, list):
            issues.append(f"{job_name} must define steps")
            continue

        uses = {step.get("uses") for step in steps if isinstance(step, dict)}
        for action in ("actions/checkout@v7", "actions/setup-python@v6"):
            if action not in uses:
                issues.append(f"{job_name} is missing action: {action}")

        runs = {step.get("run") for step in steps if isinstance(step, dict)}
        for command in EXPECTED_WORKFLOW_COMMANDS[job_name]:
            if command not in runs:
                issues.append(f"{job_name} is missing run command: {command}")

        if job_name in PYTEST_WORKFLOW_JOBS:
            if "python -m pip install pytest -r requirements-test.txt" not in runs:
                issues.append(f"{job_name} must install test requirements")

        if job_name in EXPECTED_WORKFLOW_MATRICES:
            strategy = job.get("strategy")
            matrix = strategy.get("matrix") if isinstance(strategy, dict) else None
            versions = matrix.get("python-version") if isinstance(matrix, dict) else None
            expected_versions = EXPECTED_WORKFLOW_MATRICES[job_name]
            if (
                not isinstance(versions, list)
                or len(versions) != len(set(versions))
                or set(versions) != expected_versions
            ):
                issues.append(f"{job_name} must keep the expected Python matrix without duplicates")

            setup_steps = [
                step
                for step in steps
                if isinstance(step, dict) and step.get("uses") == "actions/setup-python@v6"
            ]
            if not any(
                isinstance(step.get("with"), dict)
                and step["with"].get("python-version") == "${{ matrix.python-version }}"
                for step in setup_steps
            ):
                issues.append(f"{job_name} must configure setup-python from matrix.python-version")

    return issues


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


def test_public_release_files_exist():
    expected = (
        ROOT / "README.md",
        ROOT / "CHANGELOG.md",
        ROOT / "LICENSE",
        ROOT / "CONTRIBUTING.md",
        ROOT / "SECURITY.md",
        ROOT / ".env.example",
        ROOT / "requirements-test.txt",
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


def test_ci_workflow_matches_structured_contract():
    assert workflow_contract_issues(load_ci_workflow()) == []


def test_ci_workflow_rejects_malformed_yaml():
    with pytest.raises(yaml.YAMLError):
        load_workflow_text("jobs: [")


def test_ci_workflow_rejects_missing_job():
    workflow = deepcopy(load_ci_workflow())
    del workflow["jobs"]["contract"]

    assert "workflow is missing required job: contract" in workflow_contract_issues(workflow)


def test_ci_workflow_rejects_wrong_runner():
    workflow = deepcopy(load_ci_workflow())
    workflow["jobs"]["windows"]["runs-on"] = "ubuntu-latest"

    assert "windows must run on windows-latest" in workflow_contract_issues(workflow)


def test_ci_workflow_rejects_duplicate_matrix_version():
    workflow = deepcopy(load_ci_workflow())
    workflow["jobs"]["test"]["strategy"]["matrix"]["python-version"] = [
        "3.9",
        "3.10",
        "3.10",
        "3.12",
    ]

    assert "test must keep the expected Python matrix without duplicates" in workflow_contract_issues(workflow)


def test_ci_workflow_rejects_command_only_in_comment():
    text = WORKFLOW_PATH.read_text(encoding="utf-8").replace(
        "run: python ./scripts/henry_image.py quick_validate",
        "# run: python ./scripts/henry_image.py quick_validate",
        1,
    )

    issues = workflow_contract_issues(load_workflow_text(text))
    assert "smoke is missing run command: python ./scripts/henry_image.py quick_validate" in issues


def test_test_requirements_pin_pyyaml_for_structured_workflow_checks():
    assert (ROOT / "requirements-test.txt").read_text(encoding="utf-8") == "PyYAML==6.0.3\n"


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
