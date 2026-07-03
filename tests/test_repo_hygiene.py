from pathlib import Path


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
        ROOT / "SKILL.md",
        ROOT / "agents" / "henry-image.yaml",
        ROOT / ".github" / "workflows" / "ci.yml",
    )
    missing = [str(path.relative_to(ROOT)) for path in expected if not path.exists()]
    assert not missing, "\n".join(missing)


def test_committed_text_files_do_not_embed_disallowed_external_names():
    offenders = []
    for path in iter_text_files():
        text = path.read_text(encoding="utf-8")
        for marker in DISALLOWED_TEXT_MARKERS:
            if marker in text:
                offenders.append(f"{path.relative_to(ROOT)} contains {marker}")

    assert not offenders, "\n".join(offenders)
