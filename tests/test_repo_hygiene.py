from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKED_PATHS = (
    ROOT / "README.md",
    ROOT / "SKILL.md",
    ROOT / ".gitattributes",
    ROOT / ".gitignore",
    ROOT / "agents",
    ROOT / "docs",
    ROOT / "references",
    ROOT / "scripts",
    ROOT / "tests",
)
TEXT_SUFFIXES = {".md", ".py", ".yaml", ".yml", ".json", ".txt"}
DISALLOWED_LOCAL_PATH_MARKERS = (
    "C:" + r"\Users" + r"\HHPC",
    "/Users/" + "henry/",
    "henry-image-" + "review-",
    "\\" + ".codex" + r"\worktrees",
    "/" + ".codex/worktrees",
)


def iter_text_files():
    for path in CHECKED_PATHS:
        if path.is_file():
            yield path
            continue
        for candidate in path.rglob("*"):
            if candidate.is_file() and candidate.suffix.lower() in TEXT_SUFFIXES:
                yield candidate


def test_committed_text_files_do_not_embed_local_absolute_paths():
    offenders = []
    for path in iter_text_files():
        text = path.read_text(encoding="utf-8")
        for marker in DISALLOWED_LOCAL_PATH_MARKERS:
            if marker in text:
                offenders.append(f"{path.relative_to(ROOT)} contains {marker}")

    assert not offenders, "\n".join(offenders)
