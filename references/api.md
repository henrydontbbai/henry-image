# Henry Image CLI API

## Commands

- `probe`: emits `command: henry.probe`; environment readiness. Add `--live` for a real minimal image request.
- `generate`: emits `command: henry.generate`; text-to-image.
- `edit`: emits `command: henry.edit`; image/reference-image-to-image with optional mask.
- `batch`: emits `command: henry.batch`; JSONL tasks for generate/edit.
- `prompt`: emits `command: henry.prompt`; prompt package without API calls.
- `job-status`: emits `command: henry.job.status`; checks a detached long-running job.
- `job-diagnose`: emits `command: henry.job.diagnose`; summarizes job failure/running/completion evidence.
- `job-cancel`: emits `command: henry.job.cancel`; conservatively cancels only recorded job PIDs.
- `job-list`: emits `command: henry.job.list`; lists detached jobs.
- `job-cleanup`: emits `command: henry.job.cleanup`; removes old detached job directories.
- `quick_validate`: emits `command: henry.quick_validate`; local skill consistency checks.

## Common options

- `--prompt` or `--prompt-file`
- `--size auto|WIDTHxHEIGHT`
- `--quality low|medium|high|auto`
- `--quality standard|hd`: accepted for DALL-E-style compatible routers; providers may reject it for GPT Image routes.
- `--model <model>`
- `--image-model <model>`: model for Image API routes; defaults to `gpt-image-2` and is used by `/images/generations` and `/images/edits`.
- `--base-url <url>`: command-local base URL override. It wins over environment values. Full endpoint suffixes such as `/chat/completions`, `/responses`, `/images/generations`, or `/images/edits` are normalized back to the API root before the selected image endpoint is appended.
- `--api-key-env <NAME[,NAME]>`: command-local API key environment variable search before the built-in/default search list. The helper also checks common OpenAI/Henry/AiMaMi-compatible key names and matching `*_API_KEY` / `*_ACCESS_KEY` style variables. If a configured key returns an invalid-key error, the helper tries the next configured key before failing.
- `--route auto|responses|images`: `responses` uses Responses `image_generation`; `images` uses `/images/generations` for generate and `/images/edits` for edit; `auto` tries Responses then the matching Image API endpoint.
- `--candidate-policy auto|strict|all`: provider/base-url fallback policy. `auto` is default; `strict` only uses the first candidate; `all` enables legacy wide fallback for manual troubleshooting.
- `--n 1..10`: requested image count when the provider route supports it.
- `--output-format png|jpeg|webp`
- `--images-response-format auto|b64_json|url`: optional Image API `response_format` override. Leave `auto` for routers that reject this field.
- `--images-compat auto|openai|minimal`: Image API payload compatibility mode. `auto` starts with the OpenAI-style payload and retries once with a minimal payload when a router rejects extension fields. `minimal` sends only model/prompt/n/size plus image or mask files when editing.
- `--input-fidelity auto|high|low`: optional Image API edit field. Leave `auto` for `gpt-image-2`; use `high` only when the router/model supports it and reference preservation matters.
- `--output-compression 0..100` for jpeg/webp only
- `--background auto|opaque|transparent`
- `--moderation auto|low`
- `--partial-images 0..3`
- `--timeout <seconds>`
- `--retries <count>`
- `--dry-run`
- `--force`

`generate`, `edit`, and `batch` also support long-running job options:

- `--background-job`: start a detached local job and immediately emit `command: henry.job.start`.
- `--jobs-dir <path>`: job metadata directory; defaults to `output/imagegen/jobs`.

Use `--background-job` for complex prompts that may outlive a Codex stream or outer timeout. `--background auto|opaque|transparent` remains the image background field, so it is intentionally not used as the job switch.

`job-status` options:

- `--job <job_id-or-path>`: job id under `--jobs-dir`, job directory, or path to `job.json`.
- `--jobs-dir <path>`: directory used to resolve job ids.
- `--watch`: poll until the job reaches a final state.
- `--interval <seconds>`: poll interval for `--watch`.
- `--diagnose`: attach `outputs[0].diagnosis` while keeping the normal JSON envelope.
- `--format json|human`: default `json`; `human` prints a readable Blocker/Evidence/Next action report.
- `--tail-lines <n>`: stderr tail lines included in diagnosis; default `80`.

`job-diagnose` options:

- `job-diagnose --job <job_id-or-path>` diagnoses a job id, job directory, or `job.json`.
- `--jobs-dir <path>` resolves job ids under a custom jobs directory.
- `--format json|human`: default `human`; JSON emits a stable `henry_job_diagnosis` object.
- `--tail-lines <n>` controls `stderr_tail` length.

`job-cancel` options:

- `job-cancel --job <job_id-or-path>` cancels only the current job's recorded `child_pid`, `runner_pid`, and `pid`.
- `--dry-run` reports the exact recorded PIDs without terminating processes or writing job files.
- `--reason <text>` records a short reason in `job.json` when cancellation succeeds or fails.
- `--format json|human`: default `json`.

`job-cancel` is intentionally conservative: it does not scan the process table, match by command line, or kill a Windows process tree. If no recorded PID is active it returns `not_running`; if a recorded PID cannot be terminated it returns `cancel_failed`.

`job-list` and `job-cleanup` options:

- `job-list --jobs-dir <path>` lists known jobs.
- `job-cleanup --older-than <duration>` removes job directories older than durations like `7d`, `24h`, or `3600s`.

`quick_validate` also supports `--strict-names`.

First-use setup:
- Read `setup.md` before spending quota on a newly installed agent, a new device, or a requested dedicated Henry Image provider.
- Prefer a no-cost `generate --dry-run` to confirm environment visibility.
- A shell-local variable such as PowerShell `$env:NAME=...` or bash `export NAME=...` only affects that shell and child processes; an already-running Codex desktop app will not see it.

Candidate and route notes:
- Dedicated Henry Image provider variables win before Codex/AiMaMi discovery: `HENRY_IMAGE_BASE_URL`, `HENRY_IMAGE_API_BASE`, or `HENRY_IMAGE_API_BASE_URL` select the image API root; `HENRY_IMAGE_API_KEY`, `HENRY_IMAGE_OPENAI_API_KEY`, or `HENRY_IMAGE_ACCESS_KEY` are checked before generic OpenAI keys; `HENRY_IMAGE_MODEL` / `HENRY_IMAGE_RESPONSE_MODEL` and `HENRY_IMAGE_IMAGE_MODEL` / `HENRY_IMAGE_MODEL_IMAGE` override default models.
- When a dedicated Henry Image base URL is set and no CLI `--base-url` is passed, normal `auto` candidate selection stays on that dedicated provider and does not route through Codex/AiMaMi.
- If no dedicated Henry Image provider is configured, generation/probe attempts use the active Codex API access shape first when available: current `model_provider`, provider `base_url`, current `model`, optional catalog-derived actual upstream model, provider `wire_api`, `requires_openai_auth`, provider `env_key` / `api_key`, and local Codex auth availability. This is read-only and does not edit Codex, AiMaMi, local proxy, global shell config, `.env`, or credentials.
- If the current Codex `model` also has a matching provider entry, that model's direct provider base URL is tried after the active provider. This covers setups where Codex uses a smart router provider but each routed model also has a direct `by-provider/.../v1` entry.
- If `model_catalog_json` identifies a routed menu slug's actual upstream model, the direct provider Responses payload uses that actual model name when Henry did not pass `--model`.
- CLI `--base-url` and `--api-key-env` values still win for that single command. `--candidate-policy auto` keeps explicit `--base-url` and explicit routes narrow; `--route auto` may use controlled fallback. Use `--candidate-policy all` only when broad provider/base-url fallback is intentional. Duplicate normalized base URLs and duplicate auth values are skipped, and failures are summarized in `metadata.candidate_attempts`.
- Codex auth order:
  - `requires_openai_auth = true`: local Codex `auth.json` access token, then provider `env_key` / `api_key`, then environment API keys.
  - `requires_openai_auth = false`: provider `env_key` / `api_key`, then a no-auth local relay request, then environment API keys.
  - When using a Codex-derived provider and no explicit `--model` is passed, the Responses payload follows the current Codex configured model; direct model providers can use the catalog-derived actual upstream model name.
- Base URL auto-discovery checks OpenAI/Henry/AiMaMi/Open WebUI/Azure-compatible names such as `HENRY_IMAGE_BASE_URL`, `HENRY_IMAGE_API_BASE`, `HENRY_IMAGE_API_BASE_URL`, `OPENAI_BASE_URL`, `OPENAI_API_BASE`, `OPENAI_API_BASE_URL`, `IMAGES_OPENAI_API_BASE_URL`, `IMAGES_OPENAI_BASE_URL`, `IMAGE_OPENAI_API_BASE_URL`, `OPENAI_COMPAT_BASE_URL`, `OPENAI_COMPAT_API_BASE`, `AIMAMI_BASE_URL`, `AIMAMI_API_BASE`, `AIMAMI_API_BASE_URL`, `AIMA_BASE_URL`, `GPT_IMAGE_BASE_URL`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_BASE_URL`, `AOAI_API_BASE`, and `AOAI_ENDPOINT`, plus matching OpenAI/Henry/AiMaMi-style `*BASE*URL` / `*API_BASE` names.
- API key auto-discovery checks `HENRY_IMAGE_API_KEY`, `HENRY_IMAGE_OPENAI_API_KEY`, `HENRY_IMAGE_ACCESS_KEY`, `OPENAI_API_KEY`, `OPENAI_IMAGE_API_KEY`, `IMAGES_OPENAI_API_KEY`, `IMAGE_OPENAI_API_KEY`, `OPENAI_COMPAT_API_KEY`, `CODEX_OPENAI_API_KEY`, `AIMAMI_API_KEY`, `AIMA_API_KEY`, `GPT_IMAGE_API_KEY`, `AZURE_OPENAI_API_KEY`, `AOAI_API_KEY`, plus matching `*_API_KEY` / `*_ACCESS_KEY` style variables.
- Use `--route auto` for uncertain OpenAI-compatible routers.
- With `--route auto`, `--model` is used for Responses and `--image-model` is used for Image API fallback.
- Use `--route responses` for edits that rely on `--image-file-id` or `--mask-file-id`.
- Use `--route images` when the router only supports OpenAI-compatible Image API endpoints.
- Use `--images-compat minimal` when a router rejects OpenAI image fields but accepts a basic image-generation payload.
- `edit --route images` sends multipart `/images/edits` with `--image <path-or-url-or-data-url>` and optional `--mask`; it does not support `--image-file-id` or `--mask-file-id`.
- `--image <path-or-url>` accepts local files, HTTPS image URLs, and data image URLs for Responses and Image API edit/reference-image workflows.

## Adaptive authentication

Daily use should not require Henry to choose an auth mode. For every candidate base URL, the helper builds an internal redacted `AuthProfile` plan and sends requests with the safest matching shape:

- `bearer`: OpenAI/OpenAI-compatible default, using `Authorization` header. If present locally, `OPENAI_ORG_ID` / `OPENAI_ORGANIZATION` / `OPENAI_ORGANIZATION_ID` become `OpenAI-Organization`; `OPENAI_PROJECT` / `OPENAI_PROJECT_ID` become `OpenAI-Project`.
- `api-key-header`: Azure/AOAI-like endpoints prefer an `api-key` header. Provider config can override the header name with `api_key_header` / `api_key_header_name`.
- `no-auth`: local relays can be tried without sending any global key.

Azure/AOAI detection uses the base URL, source env/config name, and Codex provider hints. Traditional Azure REST receives an `api-version` query parameter from provider config, Azure API-version env vars, or the default `2024-10-21`. Azure `/openai/v1` or OpenAI-compatible Azure relays may try both `api-key` and Bearer shapes on the same base URL.

Local relay detection covers `localhost`, `127.0.0.1`, and `::1`. When the Codex provider does not require OpenAI auth, no-auth is first and the helper does not blindly send the global `OPENAI_API_KEY` to that local endpoint. A local relay key is considered only when it is provider-configured or explicitly passed with command-local `--api-key-env`.

Codex provider parsing is read-only. In addition to `base_url`, `env_key`, `api_key`, and `requires_openai_auth`, the helper recognizes provider fields such as `headers`, `http_headers`, `extra_headers`, `query`, `query_params`, `extra_query`, `api_version`, `api-key`, `api_key_header`, and `auth_type`.

Fallback remains safe:

- `--candidate-policy auto` may switch auth shape after 401/403 only inside the same base URL.
- Auth, policy, quota, rate-limit, and bad-parameter failures do not cross provider/base-url fallback.
- `strict` keeps only the first auth profile; `all` is reserved for manual troubleshooting.

Observability fields are safe to print: `auth_plan`, `auth_shape`, `header_names`, `query_names`, `header_sources`, `query_sources`, `provider_family`, and `adaptive_reason`. Secret values are redacted in stdout envelopes, manifests, stderr JSONL, dry-runs, job-status diagnosis, and job-diagnose output.

Scope boundary: adaptive auth covers common OpenAI-compatible, Codex-provider, Azure/AOAI, and local relay injection shapes. It does not implement OAuth refresh, browser cookie/session reuse, mTLS, HMAC/signature authentication, or provider-private image payload/response schemas. If a backend needs those, report a structured blocker or add a provider-specific adapter instead of pretending the generic route is usable.

## Prompt options

- `--package-version 1|2`: v1 keeps the legacy prompt package shape; v2 emits compiled prompt tasks and platform-specific prompt outputs.
- `--platform all|openai|flux|sdxl|midjourney`: selects v2 platform outputs. `all` includes the reusable ComfyUI slot map as documentation only.
- `--explain`: includes the compiled task and assumptions in envelope metadata.
- `--review-template auto|photo|product|social|engineering`: selects the validation checklist style for v2 prompt packages.

## Edit options

- `--image <path>` may repeat.
- `--image-file-id <id>` may repeat.
- `--mask <path>` applies to the first image.
- `--mask-file-id <id>` applies to the first image.

## JSON envelope

Every command prints one JSON object to stdout:

```json
{
  "ok": true,
  "status": "completed",
  "command": "henry.generate",
  "provider": {
    "type": "henry-responses-image-generation",
    "base_url_host": "api.openai.com",
    "responses_endpoint": "https://api.openai.com/v1/responses"
  },
  "request_id": "optional",
  "outputs": [
    {
      "index": 1,
      "path": "output/imagegen/henry-image.png",
      "bytes": 12345,
      "format": "png",
      "manifest": "output/imagegen/henry-image.png.json"
    }
  ],
  "error": null,
  "metadata": {}
}
```

Failures use `ok: false` and put the readable reason in `error.message`. When fallback was attempted, `metadata.candidate_attempts` records the base URL source, route, selected auth source / key env name, auth shape, header/query names, provider family, payload mode, and redacted error for each attempt. Probe and generated envelopes may also include `metadata.codex_access`, `metadata.auth_source`, `metadata.auth_shape`, `metadata.auth_plan`, `metadata.auth_source_set`, `metadata.api_key_env_set`, `metadata.base_url_env_set`, and `metadata.candidate_summary`. `metadata.codex_access.model_provider_candidate` appears when the current Codex model has its own direct provider entry; `metadata.codex_access.model_catalog_entry.actual_model` appears when the Codex model catalog exposes the upstream model name.

## Background jobs

`--background-job` returns quickly with:

```json
{
  "ok": true,
  "status": "running",
  "command": "henry.job.start",
  "outputs": [
    {
      "type": "henry_job",
      "job_id": "20260608T084827Z-fd851668",
      "job_path": "output/imagegen/jobs/20260608T084827Z-fd851668",
      "stdout": "output/imagegen/jobs/.../stdout.json",
      "stderr": "output/imagegen/jobs/.../stderr.jsonl",
      "result": "output/imagegen/jobs/.../stdout.json",
      "out": "output/imagegen/henry-image.png"
    }
  ]
}
```

Each job directory contains:

- `job.json`: job id, runner pid, child pid when known, original command, cwd, output paths, status, exit code, and timestamps.
- `stdout.json`: final child command JSON envelope, for example `henry.generate`; if the child exits without valid JSON, the job runner writes a structured `child_no_result` or `child_invalid_json` envelope.
- `stderr.jsonl`: progress, retry, route fallback, `request_start`, `request_finish`, and provider diagnostics.

Poll with:

```bash
python3 scripts/henry_image.py job-status --job <job_id-or-path>
```

`job-status` reports `running`, `completed`, `failed`, `cancelled`, or `not_found`. When completed, failed, or cancelled, `outputs[0].result` contains the child envelope or the structured runner fallback. Provider/API failures keep `metadata.candidate_attempts`; runner fallbacks reconstruct best-effort candidate attempts from `stderr.jsonl`. Use `--watch --interval 5` for long jobs. Add `--diagnose` or run `job-diagnose --format human` for a concise diagnosis.

Diagnosis objects contain:

- `summary`: one-line blocker/completion/running conclusion.
- `category`: normalized category such as `rate_limited`, `content_policy`, `child_no_result`, `cancelled`, or `unknown`.
- `next_action`: recommended next step.
- `evidence`: route/status/error/request/auth/base-url evidence.
- `files`: paths for `job.json`, `stdout.json`, `stderr.jsonl`, output, and manifests when known.
- `attempts`: compact candidate request chain.
- `stderr_tail`: recent stderr JSONL lines.

When `job-cancel` succeeds, `job.json` is atomically updated to `status: cancelled` with `cancelled_at`, `cancel_reason`, and `cancel_attempts`. If `stdout.json` has no valid child envelope, the helper writes a structured `job_cancelled` envelope and appends `job_cancel_requested` / `job_cancel_finish` events to `stderr.jsonl`.

## Manifest

Each successful image writes a sibling manifest JSON recording:

- provider host and endpoint
- selected route and route attempts when `--route auto` is used
- request id when available
- output paths and bytes
- prompt
- model, image model, route, payload mode, payload kind, size, quality, input fidelity, output format, background, moderation
- Codex/candidate diagnostics such as `codex_access`, `auth_source`, `auth_shape`, `auth_plan`, `header_names`, `query_names`, `provider_family`, `base_url_source`, and `candidate_attempts` when available
- latency
- creation time

## Batch JSONL

Each line is one task. A task may include any common option plus `out`, `image`, `image_file_id`, `mask`, or `mask_file_id`. Per-task compatibility fields include `route`, `base_url`, `candidate_policy`, `api_key_env`, `image_model`, `images_response_format`, `images_compat`, and `input_fidelity`. If `image` or `image_file_id` is present, the task is treated as edit; otherwise generate. Default batch files are named `henry-image-<index>.<format>`.

Batch checkpoint options:

- `--result-jsonl <path>` writes each task result as it completes; default is `<out-dir>/results.jsonl`.
- `--resume` skips successful task indexes already recorded in result JSONL.
- `--skip-existing` skips tasks whose output file already exists.
- `--max-images <n>` rejects non-dry-run batches above the requested image budget while allowing dry-run inspection.
