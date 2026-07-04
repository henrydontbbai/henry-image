# Henry Image

Henry Image is a small local image workflow project for real image delivery, prompt packaging, and job recovery.

Version: `0.2.5`

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

1. Copy the four public variables from `.env.example` into your local environment or secret manager.
2. Use `probe` when you want a readiness check, or `generate --dry-run` when you want a command preview.
3. Run a real `generate`, `edit`, or `batch` command after the route and auth sources look correct.

## First Run

Use `probe` when you want to confirm configuration without creating an image file:

```powershell
python .\scripts\henry_image.py probe `
  --route auto `
  --model response-model-v1 `
  --image-model image-model-v1
```

Use `generate --dry-run` when you want to preview the exact command contract, output path, and workflow guidance:

```powershell
python .\scripts\henry_image.py generate `
  --dry-run `
  --route auto `
  --model response-model-v1 `
  --image-model image-model-v1 `
  --prompt "Connectivity dry run" `
  --out "output\imagegen\dry-run.png"
```

## Generate

```powershell
python .\scripts\henry_image.py generate `
  --route responses `
  --model response-model-v1 `
  --image-model image-model-v1 `
  --prompt "A clean product photo of a ceramic cup" `
  --out "output\imagegen\cup.png" `
  --force
```

## Edit

```powershell
python .\scripts\henry_image.py edit `
  --route auto `
  --model response-model-v1 `
  --image-model image-model-v1 `
  --image ".\input\source.png" `
  --prompt "Replace the background with a soft studio setup" `
  --out "output\imagegen\edit.png" `
  --force
```

## Batch

Create a JSONL file with one task per line:

```json
{"prompt":"A clean product photo of a ceramic cup","out":"output/imagegen/batch/cup.png"}
{"prompt":"Replace the background with a soft studio setup","image":[".\\input\\source.png"],"out":"output/imagegen/batch/edit.png"}
```

Run the batch:

```powershell
python .\scripts\henry_image.py batch `
  --route auto `
  --model response-model-v1 `
  --image-model image-model-v1 `
  --batch-input ".\input\tasks.jsonl" `
  --out-dir "output\imagegen\batch"
```

## Job Recovery

Use `--background-job` for long-running work, then inspect the stored job records:

```powershell
python .\scripts\henry_image.py job-status --job ".\output\imagegen\jobs\job-123"
python .\scripts\henry_image.py job-diagnose --job ".\output\imagegen\jobs\job-123" --format human
python .\scripts\henry_image.py job-list
```

`job-list` reports the saved job metadata on disk. It does not probe live processes in real time.

## Output Contract

Stable top-level stdout fields:

- `ok`
- `status`
- `command`
- `provider`
- `request_id`
- `outputs`
- `error`
- `metadata`

Stable metadata fields, when present:

- `route`
- `auth_source`
- `auth_shape`
- `base_url_source`
- `replay_command`
- `next_action`
- `workflow`

Validation failures may emit only partial metadata such as `workflow`, `replay_command`, and `next_action`.

`workflow_profile` may still appear in `metadata`, but it is diagnostic and may change without compatibility guarantees.

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
- Missing prompt or invalid local input: Henry Image should return a structured `validation_error` instead of a Python traceback.
- Route validation error: use `--model` for `responses`, `--image-model` for `images`, and both for `auto`.
- Readiness check: run `python .\scripts\henry_image.py probe --route auto --model response-model-v1 --image-model image-model-v1`
- Upstream timeout: Henry Image reports a structured `timeout` error; it does not hide remote unavailability. Retry with a shorter `--timeout` for diagnosis, or treat it as a remote service issue.
- Repository health: rerun `python .\scripts\henry_image.py quick_validate`

## Release Process

Maintainers should follow `docs/release-process.md` for version rules, verification, OpenCode review, and tag creation.

## Layout

- `SKILL.md` - behavior and routing notes
- `agents/henry-image.yaml` - local agent defaults
- `references/` - short operational references
- `references/runbooks.md` - batch and recovery guidance
- `CONTRIBUTING.md` - local checks and pull request expectations
- `SECURITY.md` - private security reporting guidance
- `scripts/henry_image.py` - CLI entrypoint
- `scripts/henry_image_core/` - support modules
- `tests/` - regression coverage
- `.github/workflows/ci.yml` - minimal CI
