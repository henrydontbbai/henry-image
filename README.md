# Henry Image

Henry Image is a small local image workflow project for real image delivery, prompt packaging, and job recovery.

Version: `0.2.0`

## What it does

- generate a new image to a local file
- edit an existing image
- run JSONL batch work
- check configuration with `probe`
- build a generic prompt package with `prompt`
- manage long-running background jobs

## Public configuration

Only these public environment variables are supported:

- `HENRY_IMAGE_BASE_URL`
- `HENRY_IMAGE_API_KEY`
- `HENRY_IMAGE_MODEL`
- `HENRY_IMAGE_IMAGE_MODEL`

## Main commands

```text
generate
edit
batch
probe
prompt
job-status
job-diagnose
job-cancel
job-list
job-cleanup
quick_validate
```

## Local checks

```powershell
python -m pytest -q
python .\scripts\henry_image.py quick_validate
```

## Layout

- `SKILL.md` - behavior and routing notes
- `agents/henry-image.yaml` - local agent defaults
- `references/` - short operational references
- `scripts/henry_image.py` - CLI entrypoint
- `scripts/henry_image_core/` - support modules
- `tests/` - regression coverage
- `.github/workflows/ci.yml` - minimal CI
