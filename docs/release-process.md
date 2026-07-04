# Release Process

This repository uses a lightweight release record:

- synced version markers in the repo
- `CHANGELOG.md`
- a pushed git tag in `vX.Y.Z` format

GitHub Release pages are optional. Do not create one unless release notes, assets, or a public announcement need a dedicated page.

## Version Rules

- Patch: bug fixes, test-only hardening, CI tightening, documentation polish, and other non-breaking maintenance work
- Minor: backward-compatible CLI or workflow additions that expand the public surface
- Major: breaking changes to public commands, public environment variables, output contracts, or route behavior

## Release Checklist

1. Confirm the repo version is correct in `scripts/henry_image.py`, `README.md`, `SKILL.md`, and `CHANGELOG.md`
2. Run:

```powershell
python -m pytest -q
python .\scripts\henry_image.py quick_validate
```

3. Sync an audit worktree and ask OpenCode for a blocker review
4. Update `CHANGELOG.md` so the release entry matches the current shipped state
5. Commit the final release-ready state
6. Create the release tag:

```powershell
git tag -a vX.Y.Z -m "Henry Image vX.Y.Z"
git push origin vX.Y.Z
```

## GitHub Release Page Policy

GitHub Release is optional for this project.

Use a GitHub Release page only when at least one of these is true:

- the release needs human-readable notes beyond `CHANGELOG.md`
- the release publishes downloadable assets
- the release should be easier to browse from the repository homepage

If none apply, keep the release record as `CHANGELOG.md` plus the pushed git tag.
