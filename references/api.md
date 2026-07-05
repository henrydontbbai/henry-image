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

## Stable stdout contract

The CLI prints one JSON envelope to stdout with these stable top-level fields:

- `ok`
- `status`
- `command`
- `provider`
- `request_id`
- `outputs`
- `error`
- `metadata`

## Stable metadata fields

The stable metadata fields, when present, are:

- `route`
- `auth_source`
- `auth_shape`
- `base_url_source`
- `replay_command`
- `workflow`
- `next_action`

Validation failures may emit only partial metadata such as `workflow`, `replay_command`, and `next_action`.

`workflow_profile` may still appear in `metadata`, but it is diagnostic information and is not a compatibility promise.

## Active advanced images options

The only public route-specific advanced images options are:

- `--images-response-format`
- `--output-compression`

These options only affect requests sent through the `images` route.
`--output-compression` applies only to `jpeg` or `webp` output there.

## Output files

Successful image runs write:

- one or more local image files
- one manifest next to the output

## Generate example

```json
{
  "ok": true,
  "status": "completed",
  "command": "henry.generate",
  "provider": {
    "type": "henry-remote-service",
    "base_url_host": "images.example",
    "route": "responses",
    "base_url_source": "HENRY_IMAGE_BASE_URL"
  },
  "request_id": "req-demo",
  "outputs": [
    {
      "index": 1,
      "path": "output/imagegen/cup.png",
      "bytes": 102400,
      "format": "png",
      "manifest": "output/imagegen/cup.png.json"
    }
  ],
  "error": null,
  "metadata": {
    "route": "responses",
    "auth_source": "HENRY_IMAGE_API_KEY",
    "auth_shape": "bearer",
    "base_url_source": "HENRY_IMAGE_BASE_URL",
    "replay_command": "python scripts/henry_image.py generate --prompt 'A clean product photo of a ceramic cup' --size 1024x1024 --quality medium --route responses --model response-model-v1 --image-model image-model-v1 --output-format png --out output/imagegen/cup.png",
    "next_action": "Review the generated image and reuse this command as the starting point for the next variation.",
    "workflow": {
      "mode": "generate",
      "stage": "review",
      "replay_command": "python scripts/henry_image.py generate --prompt 'A clean product photo of a ceramic cup' --size 1024x1024 --quality medium --route responses --model response-model-v1 --image-model image-model-v1 --output-format png --out output/imagegen/cup.png",
      "source_output": null,
      "next_action": "Review the generated image and reuse this command as the starting point for the next variation."
    },
    "workflow_profile": {
      "version": 1,
      "last_mode": "generate"
    }
  }
}
```

## Batch JSONL example

```json
{"prompt":"A clean product photo of a ceramic cup","out":"output/imagegen/batch/cup.png"}
{"prompt":"Replace the background with a soft studio setup","image":[".\\input\\source.png"],"out":"output/imagegen/batch/edit.png"}
```

## Manifest example

```json
{
  "command": "henry.generate",
  "route": "responses",
  "request_id": "req-demo",
  "provider": {
    "type": "henry-remote-service",
    "base_url_host": "images.example",
    "route": "responses",
    "base_url_source": "HENRY_IMAGE_BASE_URL"
  },
  "config": {
    "base_url_source": "HENRY_IMAGE_BASE_URL",
    "auth_source": "HENRY_IMAGE_API_KEY",
    "model": "response-model-v1",
    "image_model": "image-model-v1",
    "size": "1024x1024",
    "quality": "medium",
    "output_format": "png"
  },
  "outputs": [
    {
      "index": 1,
      "path": "output/imagegen/cup.png",
      "bytes": 102400,
      "format": "png"
    }
  ],
  "metadata": {
    "route": "responses",
    "auth_source": "HENRY_IMAGE_API_KEY",
    "auth_shape": "bearer",
    "base_url_source": "HENRY_IMAGE_BASE_URL"
  }
}
```

## Failure example

```json
{
  "ok": false,
  "status": "validation_error",
  "command": "henry.generate",
  "provider": {
    "type": "henry-local-validator"
  },
  "request_id": null,
  "outputs": [],
  "error": {
    "status": null,
    "code": null,
    "type": null,
    "message": "Missing prompt. Use --prompt or --prompt-file.",
    "category": "validation_error"
  },
  "metadata": {
    "replay_command": "python scripts/henry_image.py generate --size 1024x1024 --quality medium --route responses --model response-model-v1 --image-model image-model-v1 --output-format png --out output/imagegen/henry-image.png",
    "next_action": "Fix the blocker and rerun: python scripts/henry_image.py generate --size 1024x1024 --quality medium --route responses --model response-model-v1 --image-model image-model-v1 --output-format png --out output/imagegen/henry-image.png",
    "workflow": {
      "mode": "generate",
      "stage": "setup",
      "replay_command": "python scripts/henry_image.py generate --size 1024x1024 --quality medium --route responses --model response-model-v1 --image-model image-model-v1 --output-format png --out output/imagegen/henry-image.png",
      "source_output": null,
      "next_action": "Fix the blocker and rerun: python scripts/henry_image.py generate --size 1024x1024 --quality medium --route responses --model response-model-v1 --image-model image-model-v1 --output-format png --out output/imagegen/henry-image.png"
    }
  }
}
```

## Diagnostic stance

Keep diagnostics factual:

- configuration errors should say exactly what is missing
- network or service errors should keep the remote response category
- no secret values should appear in stdout, stderr, or manifests
