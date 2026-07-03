# Henry Image Routing

Start with `workflow-map.md` for the short path. This page owns the full routing decision tree and fallback policy.

## Core rule

Text chat support is not image generation support. Treat image capability as unverified until a built-in image tool exists in the current session, Henry `probe --live` succeeds, or a real Henry `generate/edit` call returns image bytes.

Start with `quick-card.md` for a short route decision table. Use `runbooks.md` for repeatable character-board, thumbnail-board, ecommerce, edit, and batch workflows.

For first install, a new machine, or a requested dedicated image provider, read `setup.md` before real generation. Confirm the dedicated variables are visible to the current Codex process with a no-cost `--dry-run`.

## Decision tree

1. Is the request vague, casual, or mixed-language?
   - Yes: run the understanding pipeline in `references/understanding.md`, then compile the task with `references/prompt-compiler.md`.
   - No: compile the task directly with `references/prompt-compiler.md`.

2. Is Henry asking for deterministic geometry, engineering drawing, CAD-like output, 3D-printing dimensions, schematics, exact labels, or multiple views that must agree?
   - Yes: use `references/engineering-diagrams.md`. Prefer SVG/PDF/OpenSCAD/spec output. Raster image generation is only a concept preview.
   - No: continue.

3. Did Henry ask to generate, run, output, save, or produce an image?
   - Yes: use Henry CLI `generate/edit/batch`, not a prompt package, not Flux, not built-in image_gen by default, and not the current text chat model/router.
   - If this is the first use after install, or Henry expects a dedicated provider and `HENRY_IMAGE_BASE_URL` is missing from the current process, stop before real generation and give the setup steps in `setup.md`.
   - If `HENRY_IMAGE_BASE_URL` is set, pass normal Henry CLI args and let that dedicated provider win over Codex/AiMaMi discovery. This avoids using Codex chat model quota.
   - If no dedicated Henry Image base URL is set, for `gpt-image-2`, pass `--route responses --candidate-policy auto --model gpt-image-2 --image-model gpt-image-2` and omit `--base-url` so the CLI auto-selects a direct `codex/by-provider/.../v1` relay.
   - If the request is a multi-element character board, thumbnail board, infographic, complex poster, clearly long prompt, local `outputs` deliverable, or a retry after `stream disconnected before completion`: use Henry CLI `generate/edit/batch --background-job`.
   - Use built-in `image_gen` only when Henry explicitly wants a simple in-chat preview, an actual image generation tool is visible in the current session, and no local file/manifest is required.

4. Does Henry only need reusable prompts?
   - Yes: use `prompt` mode or return a prompt package. Do not choose this branch when Henry asked to generate/output/save an image.
   - No: continue.
   - If Henry asked for both a reusable prompt and an actual image, generate the image first with CLI, then optionally save the prompt package.

5. Is route capability unknown?
   - Run no-cost `probe`.
   - Run `probe --live` only when Henry explicitly wants a real capability check and accepts image quota use.
   - If a checked CLI generation/edit attempt fails and no authorized image route can produce bytes, return a prompt package with the blocker. Do not skip the CLI attempt for normal `gpt-image-2` requests.
   - For OpenAI-compatible routers, use `--route auto` when route support is uncertain. It tries Responses `image_generation` first, then `/images/generations` for generate or `/images/edits` for edit when Responses is unsupported or returns no image.
   - The helper first detects the current Codex API access path from `~/.codex/config.toml`: active `model_provider`, provider `base_url`, `wire_api`, `requires_openai_auth`, provider `env_key` / `api_key`, current `model`, and optional `model_catalog_json`; it also checks Codex `auth.json` availability without printing secrets.
   - For `gpt-image-2`, the helper additionally prefers direct providers whose configured/profile/catalog actual model is `gpt-image-2`; these image-model candidates are isolated from the smart router under `--candidate-policy auto`.
   - If the current Codex `model` has its own provider entry, the helper also tries that model's direct provider URL after the active provider. This covers Codex smart-router setups where `model_provider` points to a router but `model` points to a concrete `by-provider/.../v1` route.
   - If `model_catalog_json` exposes the routed menu model's actual upstream model, direct-provider Responses calls use that actual model name when Henry did not pass `--model`.
   - Dedicated Henry Image provider variables (`HENRY_IMAGE_BASE_URL`, `HENRY_IMAGE_API_BASE`, `HENRY_IMAGE_API_BASE_URL`) win over Codex/AiMaMi discovery. Dedicated key variables (`HENRY_IMAGE_API_KEY`, `HENRY_IMAGE_OPENAI_API_KEY`, `HENRY_IMAGE_ACCESS_KEY`) are tried before generic OpenAI keys.
   - If no dedicated provider is configured, after Codex-derived candidates, it tries environment base URL / auth candidates in priority order. Use command-local `--base-url` / `--api-key-env` to put a router or key first without editing shell config.
   - If Image API routes reject optional image fields, retry with `--images-compat minimal` or leave `--images-compat auto` so the helper can retry once with a minimal payload.
   - For edits, use `--route responses` when file IDs are required. Use `--route images` or `--route auto` when the router supports `/images/edits` and the inputs are local files, HTTPS image URLs, or data image URLs.
   - For Open WebUI-style image backends, honor `IMAGES_OPENAI_API_BASE_URL` / `IMAGES_OPENAI_API_KEY` when present.
   - For Azure-style image endpoints, detect common env names such as `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AOAI_API_BASE`, and `AOAI_API_KEY`; use `api-key` header plus `api-version` automatically for traditional Azure REST, and allow same-base `api-key`/Bearer adaptation for Azure `/openai/v1` compatible relays.

6. For each image input, declare its role using `references/roles.md`.

7. Execute `generate`, `edit`, `batch`, or `prompt`. For long-running raster work, start a background job and poll it:

```bash
python3 scripts/henry_image.py generate \
  --route auto \
  --timeout 900 \
  --retries 1 \
  --background-job \
  --prompt "A multi-element character board..." \
  --out output/imagegen/character-board.png
```

```bash
python3 scripts/henry_image.py job-status --job <job_id-or-path>
```

`--background` remains the Image API background setting (`auto|opaque|transparent`); use `--background-job` for detached local jobs.

8. Validate result against `references/review.md` and classify failures with `references/failure.md`.

## Candidate policy

- `--candidate-policy auto` is default. Explicit `--base-url` and explicit routes stay narrow; `--route auto` may use controlled fallback.
- `--candidate-policy strict` uses the first candidate only, except same-base Responses to Images route fallback.
- `--candidate-policy all` keeps legacy wide provider/base-url fallback and should be used only for manual troubleshooting.

Do not cross provider/base-url fallback on invalid credentials, content policy, quota, rate limit, or bad parameter failures unless Henry explicitly chooses `all`.

Authentication fallback is narrower than route fallback:

- OpenAI/OpenAI-compatible defaults to Bearer and may include `OpenAI-Organization` / `OpenAI-Project` if local env provides them.
- Azure/AOAI-like candidates prefer `api-key` header and add `api-version` query; default Azure version is `2024-10-21` when not configured.
- Local relay candidates prefer no-auth and do not receive the global OpenAI key unless a key is explicitly command-local or configured on that provider.
- 401/403 can switch auth shape only within the same base URL; it must not jump to another provider/base URL.
- `probe`, `--dry-run`, `stderr.jsonl`, manifests, and diagnosis show redacted `auth_plan`, `auth_shape`, `header_names`, `query_names`, `provider_family`, and `adaptive_reason`.

## Codex desktop or CLI

Use built-in `image_gen` when available only for simple previews. For deterministic local output paths, manifests, `gpt-image-2` through AiMaMi/Codex, or long-running work, run the helper:

```bash
python3 scripts/henry_image.py probe
```

`probe` checks Codex/API access readiness only. It does not prove image capability. `probe --live` performs a real minimal image request. Add `--route auto` when testing an uncertain router.

Do not put complex generation into a 120-second synchronous shell call. If a synchronous call is unavoidable, the outer timeout must be larger than the CLI `--timeout` plus retries and route fallback time; otherwise the shell can fail first with an outer timeout even though the image request is still running. Prefer `--background-job` and poll with `job-status`.

Without command-local overrides, a dedicated Henry Image provider wins first when `HENRY_IMAGE_BASE_URL`, `HENRY_IMAGE_API_BASE`, or `HENRY_IMAGE_API_BASE_URL` is set. In that mode, normal `auto` routing stays on that base URL and does not route through Codex/AiMaMi. Use:

```powershell
$env:HENRY_IMAGE_BASE_URL = "https://example-router/v1"
$env:HENRY_IMAGE_API_KEY = "<set outside chat>"
$env:HENRY_IMAGE_MODEL = "gpt-image-2"
$env:HENRY_IMAGE_IMAGE_MODEL = "gpt-image-2"
```

For persistent Windows/macOS setup and GUI app environment caveats, use `setup.md`.

If no dedicated Henry Image provider is configured, the helper reads Codex/AiMaMi config and, for `gpt-image-2` image tasks, auto-selects direct image-model providers before falling back to legacy candidates. This supports common Codex access shapes:

- active provider with `requires_openai_auth = true`: try local Codex auth token first, then provider `env_key` / `api_key`, then environment API keys;
- active provider with `requires_openai_auth = false`: try provider `env_key` / `api_key`, then no-auth local relay, then environment API keys;
- active provider with `wire_api = "responses"`: use the Responses route first and use the current Codex configured model unless Henry passed `--model`.
- smart-router provider plus direct model provider: for generic tasks, try the active router first, then the current model's direct provider entry if it exists; for `gpt-image-2` image tasks, prefer direct `gpt-image-2` providers and avoid the smart router under normal `auto` policy.
- catalog-backed routed model: use `model_catalog_json` to map a local menu slug such as `aimami_relay_*` to the actual upstream model name for direct-provider Responses calls.
- provider-injected auth: read-only `headers`, `http_headers`, `extra_headers`, `query`, `query_params`, `extra_query`, `api_version`, `api_key_header`, and `auth_type` fields can shape requests without Henry manually setting a mode.

The helper then checks discovered base URL environment names including `OPENAI_BASE_URL`, `OPENAI_API_BASE`, `OPENAI_API_BASE_URL`, `HENRY_IMAGE_BASE_URL`, `IMAGES_OPENAI_API_BASE_URL`, `IMAGES_OPENAI_BASE_URL`, `IMAGE_OPENAI_API_BASE_URL`, `OPENAI_COMPAT_BASE_URL`, `OPENAI_COMPAT_API_BASE`, `AIMAMI_BASE_URL`, `AIMAMI_API_BASE`, `AIMAMI_API_BASE_URL`, `AIMA_BASE_URL`, `GPT_IMAGE_BASE_URL`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_BASE_URL`, `AOAI_API_BASE`, and `AOAI_ENDPOINT`, plus matching OpenAI/Henry/AiMaMi-style base URL names. Full endpoint suffixes are normalized back to the API root, so these all route to the same selected image endpoint:

```text
https://router.example/v1
https://router.example/v1/chat/completions
https://router.example/v1/responses
https://router.example/v1/images/generations
https://router.example/v1/images/edits
```

## cockpit and custom API clients

Preferred path: the backend sends a Responses API request with the image generation tool. The image result is expected in `image_generation_call.result` as base64.

Minimal payload shape:

```json
{
  "model": "gpt-5",
  "input": "Generate a realistic city street photo...",
  "tools": [
    {
      "type": "image_generation",
      "size": "1024x1024",
      "quality": "medium",
      "output_format": "png"
    }
  ],
  "tool_choice": {
    "type": "image_generation"
  }
}
```

If cockpit only forwards normal chat messages, it will not produce images.

Fallback path for OpenAI-compatible routers, text-to-image:

```json
{
  "model": "gpt-image-2",
  "prompt": "Generate a realistic city street photo...",
  "n": 1,
  "size": "1024x1024"
}
```

This is sent to `/v1/images/generations`. It is useful when a router supports classic image generation but not Responses tools.

Fallback path for OpenAI-compatible routers, image edit/reference workflows:

```text
multipart/form-data POST /v1/images/edits
model=gpt-image-2
prompt=Restore the floor plan interior structure lines...
image=@reference.png
mask=@mask.png (optional)
```

This is useful when a router exposes an Image API model such as `gpt-image-2` or `image-2` but does not support Responses `image_generation`. It requires actual image files, HTTPS image URLs, or data image URLs; `image_file_id` and `mask_file_id` stay Responses-only.

Some routers accept OpenAI chat-style models but reject image-only parameters such as `quality`, `background`, `output_format`, or `response_format`. For those routers, use:

```bash
python3 scripts/henry_image.py generate \
  --route images \
  --images-compat minimal \
  --prompt "Generate a realistic city street photo..."
```

This does not prove the router can generate images. It only avoids failing early on optional field compatibility.

For edits through an Image API router:

```bash
python3 scripts/henry_image.py edit \
  --route images \
  --image-model gpt-image-2 \
  --images-compat minimal \
  --image reference.png \
  --prompt "Restore the floor plan interior structure lines."
```

Add `--input-fidelity high` only for routers/models that document it; leave it at `auto` for `gpt-image-2` unless the provider says otherwise.

## AiMaMi and OpenAI-compatible routers

Do not assume support. The default path is to let the helper read the current Codex/AiMaMi access route. If testing a specific external router, use a command-local route:

```bash
OPENAI_BASE_URL="https://example-router/v1" \
python3 scripts/henry_image.py probe --live --route auto --quality low
```

For Henry-specific credentials without changing shell configuration:

```bash
python3 scripts/henry_image.py probe \
  --api-key-env HENRY_IMAGE_API_KEY \
  --base-url "https://example-router/v1" \
  --route auto
```

If all candidate routes reject `image_generation` or return no image bytes, fall back to `prompt` and report the final blocker plus `candidate_attempts` when available.

## Codex++

Treat Codex++ as either a built-in image tool environment or an API-style environment. Use the helper for local output, batch jobs, manifests, and explicit base URL tests.

## Output locations

Use `output/imagegen/` in the active workspace. Avoid writing generated images directly under home directories unless the user names that destination.

Background jobs write metadata under `output/imagegen/jobs/<job_id>/` by default:

- `job.json`: job id, pid, command, cwd, output paths.
- `stdout.json`: final Henry JSON envelope from the child command.
- `stderr.jsonl`: retry and route diagnostics.
