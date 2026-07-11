# Contributing

Thank you for helping maintain Henry Image.

## Local Checks

Run these commands before opening a pull request:

```powershell
python -m pip install pytest -r requirements-test.txt
python -m pytest -q
python .\scripts\henry_image.py quick_validate
```

Workflow semantics are verified by pytest in `tests/test_repo_hygiene.py`. The
dependency-free `quick_validate` command continues to check the local CLI and
documentation contract.

## Pull Request Expectations

- keep the public Henry-only contract intact
- update `CHANGELOG.md` when user-visible behavior changes
- keep documentation and examples aligned with the shipped CLI
- prefer small, focused pull requests over broad refactors
- say in the PR description whether the change needs a release; test-only, CI-only, and docs-only maintenance PRs normally do not

## Versioning Notes

- update `scripts/henry_image.py`, `README.md`, `SKILL.md`, and `CHANGELOG.md` together when the version changes
- use `docs/release-process.md` for release checks and tag creation
- do not bump the version for maintenance-only PRs unless shipped user-visible behavior or the public contract changed
