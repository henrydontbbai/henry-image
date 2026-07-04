from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
CHECKED_PATHS = (
    ROOT / "README.md",
    ROOT / "CHANGELOG.md",
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


def test_public_release_files_exist():
    expected = (
        ROOT / "README.md",
        ROOT / "CHANGELOG.md",
        ROOT / "LICENSE",
        ROOT / ".env.example",
        ROOT / "SKILL.md",
        ROOT / "agents" / "henry-image.yaml",
        ROOT / ".github" / "workflows" / "ci.yml",
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
        "## Troubleshooting",
        ".env.example",
        "python -m pytest -q",
        "python .\\scripts\\henry_image.py generate",
        "python .\\scripts\\henry_image.py quick_validate",
    ):
        assert expected in text


def test_public_version_markers_are_in_sync():
    script_text = (ROOT / "scripts" / "henry_image.py").read_text(encoding="utf-8")
    readme_text = (ROOT / "README.md").read_text(encoding="utf-8")
    skill_text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    changelog_text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    version_match = re.search(r'HENRY_IMAGE_VERSION = "([^"]+)"', script_text)
    assert version_match
    version = version_match.group(1)

    assert f"Version: `{version}`" in readme_text
    assert f"V{version}" in skill_text
    assert f"## {version} -" in changelog_text


def test_ci_workflow_has_layered_jobs_and_python_matrix():
    text = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    for expected in (
        "smoke:",
        "hygiene:",
        "contract:",
        "test:",
        "matrix:",
        'python-version: ["3.11", "3.12"]',
        "python ./scripts/henry_image.py --help",
        "python ./scripts/henry_image.py generate --help",
        "python ./scripts/henry_image.py quick_validate",
        "python -m pytest -q tests/test_repo_hygiene.py",
        "python -m pytest -q tests/test_contract.py tests/test_jobs.py tests/test_workflow_profile.py",
        "python -m pytest -q",
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
