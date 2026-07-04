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

Example values are shown in `.env.example`.

## Quick Start

1. Set the four public `HENRY_IMAGE_*` variables in your shell or local secret manager.
2. Run a dry run to confirm the route and auth sources are visible.
3. Run a real `generate` command once the dry run looks correct.

Dry run:

```powershell
python .\scripts\henry_image.py generate `
  --dry-run `
  --route auto `
  --model response-model-v1 `
  --image-model image-model-v1 `
  --prompt "Connectivity dry run" `
  --out "output\imagegen\dry-run.png"
```

Generate:

```powershell
python .\scripts\henry_image.py generate `
  --route responses `
  --model response-model-v1 `
  --image-model image-model-v1 `
  --prompt "A clean product photo of a ceramic cup" `
  --out "output\imagegen\cup.png" `
  --force
```

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

## Troubleshooting

- Missing configuration: confirm all four `HENRY_IMAGE_*` variables are set in the current process.
- Route validation error: use `--model` for `responses`, `--image-model` for `images`, and both for `auto`.
- Readiness check: run `python .\scripts\henry_image.py probe --route auto --model response-model-v1 --image-model image-model-v1`
- Repository health: rerun `python .\scripts\henry_image.py quick_validate`

## Layout

- `SKILL.md` - behavior and routing notes
- `agents/henry-image.yaml` - local agent defaults
- `references/` - short operational references
- `scripts/henry_image.py` - CLI entrypoint
- `scripts/henry_image_core/` - support modules
- `tests/` - regression coverage
- `.github/workflows/ci.yml` - minimal CI
