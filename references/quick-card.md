# Henry Image Route Quick Card

Start with `workflow-map.md` if you need the big picture. This page is the fast route chooser and command card.

Use this page first when deciding how to run an image task.

For first install, new machine setup, or dedicated provider configuration, read `setup.md` before real generation. Do a `--dry-run` first; do not ask Henry to paste secrets into chat.

## Fast route choice

| Task | Recommended route |
| --- | --- |
| Henry says generate/run/output/save an image | CLI `generate` / `edit` |
| Local output, manifest, repeatability | CLI `generate` / `edit` |
| Explicit simple in-chat preview with actual image tool visible | built-in `image_gen` only if Henry does not need local files/manifests |
| Character board, thumbnail board, infographic, complex poster, long prompt | CLI `--background-job` |
| Batch variants or image sets | CLI `batch --background-job` |
| Router support uncertain | for normal `gpt-image-2`, run CLI dry-run/`probe`; do not switch to Flux/router/prompt-only before a checked CLI attempt |
| Prompt-only requested or checked CLI generation failure | `prompt` package |
| CAD-like, exact dimensions, manufacturing communication | SVG/PDF/OpenSCAD/spec, not raster |

## Windows PowerShell templates

No-cost dedicated provider check:

```powershell
$script = "$HOME\.codex\skills\henry-image\scripts\henry_image.py"
python $script generate --dry-run --route auto --candidate-policy auto --model gpt-image-2 --image-model gpt-image-2 --prompt "connectivity dry run" --out "output\imagegen\dry-run.png"
```

```powershell
$script = "$HOME\.codex\skills\henry-image\scripts\henry_image.py"
python $script generate --route responses --candidate-policy auto --model gpt-image-2 --image-model gpt-image-2 --prompt "A concise prompt..." --out "output\imagegen\image.png" --force
```

```powershell
python $script generate --route responses --candidate-policy auto --model gpt-image-2 --image-model gpt-image-2 --background-job --timeout 900 --prompt "A multi-element character board..." --out "output\imagegen\character-board.png" --force
python $script job-status --job <job_id-or-path> --watch --interval 5
python $script job-status --job <job_id-or-path> --diagnose
python $script job-diagnose --job <job_id-or-path> --format human
python $script job-cancel --job <job_id-or-path> --dry-run
```

## macOS / Bash templates

No-cost dedicated provider check:

```bash
script="$HOME/.codex/skills/henry-image/scripts/henry_image.py"
python3 "$script" generate --dry-run --route auto --candidate-policy auto --model gpt-image-2 --image-model gpt-image-2 --prompt "connectivity dry run" --out output/imagegen/dry-run.png
```

```bash
script="$HOME/.codex/skills/henry-image/scripts/henry_image.py"
python3 "$script" generate --route responses --candidate-policy auto --model gpt-image-2 --image-model gpt-image-2 --prompt "A concise prompt..." --out output/imagegen/image.png --force
```

```bash
python3 "$script" generate --route responses --candidate-policy auto --model gpt-image-2 --image-model gpt-image-2 --background-job --timeout 900 --prompt "A multi-element character board..." --out output/imagegen/character-board.png --force
python3 "$script" job-status --job <job_id-or-path> --watch --interval 5
python3 "$script" job-status --job <job_id-or-path> --diagnose
python3 "$script" job-diagnose --job <job_id-or-path> --format human
python3 "$script" job-cancel --job <job_id-or-path> --dry-run
```

## Long job troubleshooting

1. Run `job-status --job <job_id-or-path> --diagnose` for a JSON-safe status plus diagnosis.
2. Run `job-diagnose --job <job_id-or-path> --format human` for a readable Blocker / Evidence / Next action report.
3. If the job is stuck, run `job-cancel --job <job_id-or-path> --dry-run` first, then `job-cancel --job <job_id-or-path>` only if the listed recorded PIDs are expected.

`job-cancel` is conservative: it only targets the job's recorded `child_pid`, `runner_pid`, and `pid`; it does not scan all processes or kill a Windows process tree.

## Candidate policy

- `--candidate-policy auto`: default. Explicit `--base-url` and explicit routes stay narrow; `--route auto` may use controlled fallback.
- `--candidate-policy strict`: first candidate only, except same-base Responses to Images route fallback.
- `--candidate-policy all`: legacy wide provider/base-url fallback for manual troubleshooting.

Do not use `all` casually. It can try more configured providers than expected.

If a dedicated Henry Image provider is configured, `HENRY_IMAGE_BASE_URL` wins and `auto` stays on that provider. If no dedicated provider is configured, normal `gpt-image-2` generation should omit `--base-url`; the CLI auto-discovers direct `codex/by-provider/.../v1` image relays from the Codex/AiMaMi config and avoids using the smart router as the final image route.

## Adaptive auth quick view

Default is auto-detect; Henry should not need to choose an auth mode for normal use.

| Environment | Default auth shape |
| --- | --- |
| OpenAI / OpenAI-compatible | Bearer `Authorization`; optional `OpenAI-Organization` / `OpenAI-Project` headers when local env has them |
| Azure / AOAI traditional REST | `api-key` header + `api-version` query, default version `2024-10-21` |
| Azure `/openai/v1` compatible relay | Try same-base `api-key` then Bearer before failing |
| Local relay | Try no-auth first; do not blindly send global OpenAI key |
| Codex provider config | Read-only `headers` / `query` / `api_version` / `api_key_header` / `auth_type` hints |

For troubleshooting without spending quota:

```powershell
python $script probe --route auto
python $script generate --dry-run --route auto --prompt "test" --out "output\imagegen\dry.png"
```

Look for redacted `auth_plan`, `auth_shape`, `header_names`, `query_names`, `provider_family`, and `adaptive_reason`. Secret values must never appear.

## Failure quick actions

| Error/status | Next action |
| --- | --- |
| `stream_disconnected` | Switch complex work to CLI `--background-job`. |
| `outer_timeout` | Do not run synchronously under a short shell timeout; use background job. |
| `missing_credentials` / `invalid_credentials` | Inspect redacted `auth_plan` / `auth_shape`; do not paste secrets or cross provider automatically. |
| `rate_limited` / `quota_exceeded` | Stop or choose an explicitly authorized provider; do not auto-fallback. |
| `content_policy` | Revise prompt; do not route-fallback. |
| `bad_parameter` | Use `--images-compat minimal` or adjust size/quality/model. |
| `no_image_result` / `unsupported_router` | Use CLI `--route auto`/Image API fallback first; return prompt package only after checked CLI failure or explicit prompt-only request. |
| `cancel_failed` / `not_running` | Use `job-diagnose --format human`; do not broaden process termination automatically. |
| repeated text/dimension failures | Switch to deterministic SVG/PDF/OpenSCAD/spec. |
