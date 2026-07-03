# Henry Image Workflow Map

Use this page first. It is the shortest path through Henry Image.

## Workflow Map

```text
first-use/setup
-> choose mode
-> generate/edit/batch/prompt/probe
-> review output
-> recover/retry
```

## First-Use / Setup

- If dedicated provider setup is expected, read `setup.md` first.
- Run a no-cost `--dry-run` or `probe` before real generation.
- Do not paste secrets into chat.

## Choose Mode

| Need | Mode |
| --- | --- |
| New local image | `generate` |
| Change an existing image | `edit` |
| Multiple tasks or variants | `batch` |
| Provider/readiness diagnosis | `probe` / `probe-image-providers` |
| Reusable prompts only | `prompt` |
| Exact dimensions / deterministic engineering drawings | SVG/PDF/OpenSCAD/spec |

## Generate / Edit / Batch

- Default real-image path is Henry CLI.
- For `gpt-image-2`, default to `--route responses --candidate-policy auto`.
- Use `--background-job` for long or complex work.

## Review

Use `review.md` before calling a run successful.

## Recover / Retry

- Use `failure.md` for blocker classification.
- Use `job-status --diagnose` or `job-diagnose --format human` for background work.
- Use `job-cancel --dry-run` before cancellation.
