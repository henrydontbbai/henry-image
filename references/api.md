# API Notes

## Commands

- `generate`
- `edit`
- `batch`
- `probe`
- `prompt`
- `job-status`
- `job-diagnose`
- `job-cancel`
- `job-list`
- `job-cleanup`
- `quick_validate`

## Public variables

- `HENRY_IMAGE_BASE_URL`
- `HENRY_IMAGE_API_KEY`
- `HENRY_IMAGE_MODEL`
- `HENRY_IMAGE_IMAGE_MODEL`

## Explicit overrides

- `--base-url`
- `--api-key-env`

## Route rules

- `responses` needs `--model`
- `images` needs `--image-model`
- `auto` needs both

## Output envelope

The CLI prints one JSON envelope to stdout.

Typical metadata stays neutral and may include:

- `route`
- `auth_source`
- `base_url_source`
- `replay_command`
- `workflow`
- `workflow_profile`
- `next_action`

## Output files

Successful image runs write:

- one or more local image files
- one manifest next to the output

## Diagnostic stance

Keep diagnostics factual:

- configuration errors should say exactly what is missing
- network or service errors should keep the remote response category
- no secret values should appear in stdout, stderr, or manifests
