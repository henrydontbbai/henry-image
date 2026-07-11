# Henry Image

Henry Image is a small local image workflow project for real image delivery, prompt packaging, and job recovery.

Version: `1.0.1`

Supported runtime: Python `3.9+` on Windows, Linux, and macOS. Verified process-identity cancellation is available on Windows and Linux; macOS safely refuses unverified cancellation.

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

New jobs store a platform process identity so `job-cancel` does not terminate a reused PID. Legacy jobs without identity metadata can still report as running, but cancellation is refused with `identity_unverified`. Verified cancellation may finish as `cancelled`, remain `cancel_pending`, or fail as `cancel_failed`.

## Images Route Options

The public CLI keeps only these route-specific advanced images options:

- `--images-response-format`
- `--output-compression`

These options only affect requests sent through the `images` route.
`--output-compression` applies only to `jpeg` or `webp` output there.
Use `--route images` when `--n` is greater than `1`; `responses` and `auto` reject multiple outputs before sending a request.

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

PNG, JPEG, and WebP bytes are checked against the requested format. Images and the manifest are staged and committed as one bundle; failed commits restore previous files when `--force` is used.

`--background-job` cannot be combined with `--dry-run`. Invalid successful-response shapes and local output write failures return structured validation errors instead of Python tracebacks.

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
- Unsafe redirect or image URL: API authentication never follows a cross-origin redirect; image downloads allow HTTP(S) CDN redirects only when every resolved address is public, and reject HTTPS downgrade, non-HTTP(S) URLs, and non-public targets.
- Removed legacy advanced flags: if an older command still passes low-value tuning flags, remove them and rerun with the current help output.
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
