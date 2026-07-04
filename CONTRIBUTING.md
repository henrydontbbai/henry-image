# Contributing

Thank you for helping maintain Henry Image.

## Local Checks

Run these commands before opening a pull request:

```powershell
python -m pytest -q
python .\scripts\henry_image.py quick_validate
```

## Pull Request Expectations

- keep the public Henry-only contract intact
- update `CHANGELOG.md` when user-visible behavior changes
- keep documentation and examples aligned with the shipped CLI
- prefer small, focused pull requests over broad refactors

## Versioning Notes

- update `scripts/henry_image.py`, `README.md`, `SKILL.md`, and `CHANGELOG.md` together when the version changes
- use `docs/release-process.md` for release checks and tag creation
