---
name: henry-image
description: Use when Henry asks to generate, edit, save, diagnose, or batch image work with Henry Image V0.2.6. Use the CLI for real image delivery and use prompt output only when prompt output is explicitly requested or image delivery is blocked.
---

# Henry Image V0.2.6

## Purpose

Henry Image is the single image workflow entrypoint for this project.

Use it for:

- real image generation with local files and manifests
- edit and continuation work from an existing image
- batch image jobs
- prompt packaging when prompt output is the requested result
- readiness checks and recovery work

## Core rules

- For real image delivery, use `generate`, `edit`, or `batch`.
- For reusable prompt output only, use `prompt`.
- For readiness checks, use `probe`.
- Keep secrets out of chat.
- Do not guess missing configuration.
- For exact-dimension or production-spec work, switch to SVG, PDF, or a written spec instead of trusting raster pixels.

## Configuration contract

Only these public variables are supported:

- `HENRY_IMAGE_BASE_URL`
- `HENRY_IMAGE_API_KEY`
- `HENRY_IMAGE_MODEL`
- `HENRY_IMAGE_IMAGE_MODEL`

Advanced override:

- `--base-url`
- `--api-key-env`

## Route contract

- `--route responses` requires `model`
- `--route images` requires `image-model`
- `--route auto` requires both

Missing values are configuration errors and should be reported plainly.

## Output contract note

- top-level JSON envelope fields are stable
- `route`, `auth_source`, `auth_shape`, `base_url_source`, `replay_command`, `next_action`, and `workflow` are stable metadata fields
- `workflow_profile` is diagnostic metadata and may change without compatibility guarantees

## Workflow

1. confirm setup with `references/setup.md` when needed
2. choose the mode with `references/routing.md`
3. run the CLI
4. review the result with `references/review.md`
5. recover or retry with `references/failure.md`

## Read next

- [references/workflow-map.md](./references/workflow-map.md)
- [references/quick-card.md](./references/quick-card.md)
- [references/setup.md](./references/setup.md)
- [references/routing.md](./references/routing.md)
- [references/api.md](./references/api.md)
