---
name: henry-image
description: Use when Henry asks to generate, edit, run, save, diagnose, or manage AI image outputs with Henry Image V0.1.6, especially local PNG outputs, manifests, background jobs, gpt-image-2 via AiMaMi/Codex, or image route checks. Also use for prompt-only packages only when Henry explicitly asks for reusable prompts. For CAD-like or dimension-critical diagrams, prefer deterministic SVG/PDF/OpenSCAD/spec output over raster generation.
---

# Henry Image V0.1.6

## Purpose

`$henry-image` / `henry-image` is Henry's single image workflow entrypoint.

Use it for:

- vague, casual, or mixed-language image requests;
- real image generation with local files and manifests;
- image edits, retries, and continuation from previous output;
- batch image jobs and long-running background work;
- provider readiness checks and route diagnosis;
- prompt-only packages only when Henry explicitly asks for prompts or a checked CLI attempt cannot return real image bytes.

Do not route Henry image-output requests through old duplicate skills, Flux prompt channels, the current text chat router, or prompt-only packaging unless Henry explicitly asks for prompts only.

When Henry asks to generate, run, produce, save, or output an image, you must actually call the Henry CLI `generate` / `edit` / `batch` path. Do not stop at a prompt package. Do not treat built-in preview or text chat as a PNG substitute.

Do not treat this skill as an unlimited backend aggregator. Real generation should use Henry CLI routes that can return image bytes: OpenAI Responses `image_generation`, OpenAI-compatible `/images/generations`, and OpenAI-compatible `/images/edits`.

For `gpt-image-2` in this Codex/AiMaMi environment, the default execution shape is:

```powershell
python "$HOME\.codex\skills\henry-image\scripts\henry_image.py" generate `
  --route responses `
  --candidate-policy auto `
  --model gpt-image-2 `
  --image-model gpt-image-2 `
  --prompt "..." `
  --out "output\imagegen\image.png" `
  --force
```

If Henry Image dedicated provider variables are set, use them first and do not route through Codex/AiMaMi:

```text
HENRY_IMAGE_BASE_URL       OpenAI-compatible API root
HENRY_IMAGE_API_KEY        API key for that image route
HENRY_IMAGE_MODEL          Responses route model, optional
HENRY_IMAGE_IMAGE_MODEL    Image API route model, optional
```

Never modify AiMaMi, cockpit, Codex++, local proxy, global shell config, `.env`, or credentials while using this skill.
Never silently switch paid providers, proxy routes, or model families.

## Workflow Map

Start with [references/workflow-map.md](./references/workflow-map.md). The workflow is always:

1. first-use/setup
2. choose mode
3. run `generate` / `edit` / `batch` / `prompt` / `probe`
4. quality review
5. recover/retry

## First-Use Setup

When this skill is used after install, or when Henry expects a dedicated image provider and the current process cannot see `HENRY_IMAGE_BASE_URL`, stop before real generation and use [references/setup.md](./references/setup.md).

Rules:

- do not ask Henry to paste secrets into chat;
- ask him to set local environment variables, restart Codex/Desktop if needed, then run a no-cost `--dry-run` or `probe`;
- for Windows/macOS differences, always use `setup.md`.

Seeing `gpt-image-2` in Codex/AiMaMi does not prove image generation works. Henry Image must distinguish:

- `model_visible`
- `endpoint_reachable`
- `image_generation_verified`

## Choose Mode

Use this routing shape first:

| Need | Mode |
| --- | --- |
| New raster image with local output | `generate` |
| Modify an existing image or continue from a prior output | `edit` |
| Many variants / many tasks | `batch` |
| Readiness / route / provider diagnosis | `probe` or `probe-image-providers` |
| Reusable prompts only | `prompt` |
| deterministic engineering drawings / dimension-critical output | SVG/PDF/OpenSCAD/spec |

Built-in `image_gen` is allowed only for explicit simple in-chat preview when a real image tool is visible and Henry does not need local files or manifests.

For deterministic engineering drawings, CAD-like diagrams, dimension-critical assets, or 3D-printing communication, prefer deterministic SVG/PDF/OpenSCAD/spec output. Raster generation is concept preview only.

## Prompt Understanding

Use [references/understanding.md](./references/understanding.md) before generating when the request is vague, casual, or mixed-language.

Understanding pipeline:

```text
raw user description
-> identify image type
-> extract subject, scene, style, composition, size, usage, constraints
-> classify input image roles
-> safely fill missing details
-> detect conflicts or missing high-impact intent
-> choose execution route
-> execute CLI generate/edit for image-output requests; use prompt package only for explicit prompt-only requests or checked CLI failure
-> review output
-> retry with a targeted correction or switch output form
```

Primary image types:

- `photo-realistic`
- `product-render`
- `social-cover`
- `poster`
- `avatar`
- `logo-concept`
- `UI/mockup`
- `infographic`
- `engineering-concept`
- `transparent-cutout`
- `image-edit`
- `reference-to-image`
- `batch-variants`

## Prompt Compiler

Compile requests through [references/prompt-compiler.md](./references/prompt-compiler.md) before generating or packaging.

Canonical schema:

```text
Use case:
Output intent:
Subject:
Scene:
Style:
Composition:
Lighting:
Color/material:
Text requirements:
Input image roles:
Hard constraints:
Negative constraints:
Execution route:
Validation checklist:
```

## Input Image Roles

Classify every input before prompting or editing. This section is mandatory.

Input Image Roles:

- edit target
- visual reference
- style reference
- dimensional sketch
- feedback annotation
- previous output
- negative example

Treat red boxes, handwritten notes, UI chrome, and correction screenshots as instructions, not final visual content, unless Henry explicitly asks to reproduce them.

For role handling details, use [references/roles.md](./references/roles.md).

## Route Defaults

Use [references/quick-card.md](./references/quick-card.md) first for copyable command templates, then [references/routing.md](./references/routing.md) for the full decision tree.

Default rules:

- for real image generation, use Henry CLI `generate/edit/batch`;
- for `gpt-image-2`, default to `--route responses --candidate-policy auto --model gpt-image-2 --image-model gpt-image-2`;
- if no dedicated provider is configured, omit `--base-url` and let Henry Image discover direct image relays from Codex/AiMaMi;
- for uncertain support, use `probe` first and `probe-image-providers --format human` for provider-level readiness;
- for complex long-running work, use `--background-job`;
- for prompt-only needs, use `prompt`;
- for checked CLI failure that still cannot return bytes, only then fall back to `prompt-packages.md`.

Adaptive auth is automatic. Henry should not need to choose an auth mode for normal use. Logs, manifests, dry-runs, and diagnosis must show only redacted `auth_plan`, `auth_shape`, `header_names`, `query_names`, `provider_family`, and `adaptive_reason`, never secrets.

OpenAI / OpenAI-compatible defaults to Bearer with optional `OpenAI-Organization` and `OpenAI-Project` headers when local env provides them.

## Happy Paths

### Generate

Use `generate` for new raster images when Henry needs a local PNG and manifest.

### Edit

Use `edit` when Henry wants to continue from an existing image, keep the subject, replace the background, or refine a prior output.

### Batch

Use `batch` for multi-image runs, thumbnail boards, repeated variants, and reusable JSONL tasks.

### Prompt

Use `prompt` only for reusable prompt packages, explicit prompt-only asks, or checked CLI generation failure. If the result is only a prompt package and no PNG/local image exists, the image-generation request is not complete.

### Probe

Use `probe` for no-cost environment readiness and `probe --live` only when Henry explicitly wants a quota-spending capability check.

## Background Jobs And Recovery

Use `--background-job` for character boards, thumbnail boards, infographics, complex posters, clearly long prompts, or after `stream disconnected before completion`.

Recovery commands:

- `job-status --job <job_id-or-path>`
- `job-status --job <job_id-or-path> --diagnose`
- `job-diagnose --job <job_id-or-path> --format human`
- `job-cancel --job <job_id-or-path> --dry-run`

`job-cancel` is conservative. It only targets recorded PIDs. It does not kill Windows process trees or scan unrelated processes.

## Output Contract

The helper prints one JSON envelope to stdout and now adds workflow metadata for the happy path and the recovery path.

Expect:

- local output files under `output/imagegen/`
- sibling manifest JSON
- workflow metadata with `replay_command`, `next_action`, and `workflow_profile`

## Failure Policy

Read [references/failure.md](./references/failure.md) before claiming a retry path.

Failure Policy rules:

- state the exact blocker;
- do not ask Henry to paste secrets in chat;
- do not silently switch paid providers, proxy routes, or model families;
- do not broad-fallback across providers for invalid credentials, content-policy, quota, rate-limit, or bad-parameter failures;
- return a prompt package only when a checked CLI path still cannot produce real image bytes, or Henry explicitly asked for prompt-only output.

## Quality Review

Use [references/review.md](./references/review.md) before claiming success.

Quality Review must check:

- subject correctness
- style correctness
- text accuracy
- role handling
- annotation leakage
- multi-view consistency
- transparent/cutout quality
- whether deterministic output is now the better path

## Read Next

Use these references as deep-water material, not as the main path:

- [references/workflow-map.md](./references/workflow-map.md)
- [references/quick-card.md](./references/quick-card.md)
- [references/routing.md](./references/routing.md)
- [references/understanding.md](./references/understanding.md)
- [references/prompt-compiler.md](./references/prompt-compiler.md)
- [references/review.md](./references/review.md)
- [references/failure.md](./references/failure.md)
- [references/prompt-packages.md](./references/prompt-packages.md)
- [references/runbooks.md](./references/runbooks.md)
- [references/engineering-diagrams.md](./references/engineering-diagrams.md)
