# Henry Image Setup

Use this page when Henry Image is newly installed, moved to a new machine, or expected to use a dedicated image API route instead of the current Codex/AiMaMi model route.

## Required variables

```text
HENRY_IMAGE_BASE_URL       OpenAI-compatible API root, for example https://router.example/v1
HENRY_IMAGE_API_KEY        API key for that image route
HENRY_IMAGE_MODEL          Responses route model, usually gpt-image-2
HENRY_IMAGE_IMAGE_MODEL    Image API route model, usually gpt-image-2
```

Optional aliases:

```text
HENRY_IMAGE_API_BASE
HENRY_IMAGE_API_BASE_URL
HENRY_IMAGE_OPENAI_API_KEY
HENRY_IMAGE_ACCESS_KEY
HENRY_IMAGE_RESPONSE_MODEL
HENRY_IMAGE_MODEL_IMAGE
```

Never ask Henry to paste the real API key into chat. Use redacted checks such as `set(len=...)`.

## First-use agent behavior

When this skill is triggered after install or on a new device:

1. Do a no-cost environment check before real generation.
2. If `HENRY_IMAGE_BASE_URL` or key variables are missing in the Codex process, explain that shell-local variables are not enough for an already-running Codex app.
3. Give the OS-specific setup commands below.
4. Ask Henry to restart Codex/Desktop if the variables are set outside the current process.
5. Verify with `--dry-run` first. Use `probe --live` or real generation only when Henry explicitly accepts quota use.

## Windows PowerShell

Temporary for the current PowerShell only:

```powershell
$env:HENRY_IMAGE_BASE_URL = "https://router.example/v1"
$env:HENRY_IMAGE_API_KEY = "<set locally, do not paste into chat>"
$env:HENRY_IMAGE_MODEL = "gpt-image-2"
$env:HENRY_IMAGE_IMAGE_MODEL = "gpt-image-2"
```

This only affects commands started from that same PowerShell. It does not update an already-running Codex app.

Persist for the current Windows user:

```powershell
[Environment]::SetEnvironmentVariable('HENRY_IMAGE_BASE_URL', 'https://router.example/v1', 'User')
[Environment]::SetEnvironmentVariable('HENRY_IMAGE_API_KEY', '<set locally, do not paste into chat>', 'User')
[Environment]::SetEnvironmentVariable('HENRY_IMAGE_MODEL', 'gpt-image-2', 'User')
[Environment]::SetEnvironmentVariable('HENRY_IMAGE_IMAGE_MODEL', 'gpt-image-2', 'User')
```

Then fully restart Codex/Desktop. New terminals and new app processes should see the variables.

No-cost Windows check:

```powershell
$names = 'HENRY_IMAGE_BASE_URL','HENRY_IMAGE_API_KEY','HENRY_IMAGE_MODEL','HENRY_IMAGE_IMAGE_MODEL'
foreach ($scope in 'Process','User','Machine') {
  foreach ($name in $names) {
    $v = [Environment]::GetEnvironmentVariable($name, $scope)
    if ($name -eq 'HENRY_IMAGE_API_KEY' -and $v) {
      "$scope $name set(len=$($v.Length))"
    } elseif ($v) {
      "$scope $name $v"
    } else {
      "$scope $name missing"
    }
  }
}
```

## macOS / zsh

Temporary for the current terminal:

```bash
export HENRY_IMAGE_BASE_URL="https://router.example/v1"
export HENRY_IMAGE_API_KEY="<set locally, do not paste into chat>"
export HENRY_IMAGE_MODEL="gpt-image-2"
export HENRY_IMAGE_IMAGE_MODEL="gpt-image-2"
```

This only affects commands started from that terminal.

Persist for new zsh terminal sessions:

```bash
cat >> "$HOME/.zshrc" <<'EOF'
export HENRY_IMAGE_BASE_URL="https://router.example/v1"
export HENRY_IMAGE_API_KEY="<set locally, do not paste into chat>"
export HENRY_IMAGE_MODEL="gpt-image-2"
export HENRY_IMAGE_IMAGE_MODEL="gpt-image-2"
EOF
```

Then open a new terminal or run:

```bash
source "$HOME/.zshrc"
```

For a macOS GUI app launched from Dock/Finder, shell startup files may not be inherited. Prefer launching Codex from a terminal that already has the variables, or set the launchd user environment for the current login session:

```bash
launchctl setenv HENRY_IMAGE_BASE_URL "https://router.example/v1"
launchctl setenv HENRY_IMAGE_API_KEY "<set locally, do not paste into chat>"
launchctl setenv HENRY_IMAGE_MODEL "gpt-image-2"
launchctl setenv HENRY_IMAGE_IMAGE_MODEL "gpt-image-2"
```

Then fully quit and reopen Codex. `launchctl setenv` affects the current login session; repeat after logout/reboot unless Henry has a preferred secret manager or launch-agent setup.

No-cost macOS check:

```bash
for name in HENRY_IMAGE_BASE_URL HENRY_IMAGE_API_KEY HENRY_IMAGE_MODEL HENRY_IMAGE_IMAGE_MODEL; do
  value="${!name:-}"
  if [ "$name" = "HENRY_IMAGE_API_KEY" ] && [ -n "$value" ]; then
    echo "$name set(len=${#value})"
  elif [ -n "$value" ]; then
    echo "$name $value"
  else
    echo "$name missing"
  fi
done
```

## No-cost Henry Image verification

From Windows PowerShell:

```powershell
$script = "$HOME\.codex\skills\henry-image\scripts\henry_image.py"
python $script generate --dry-run --route auto --candidate-policy auto --model gpt-image-2 --image-model gpt-image-2 --prompt "connectivity dry run" --out "output\imagegen\dry-run.png"
```

From macOS/Linux:

```bash
script="$HOME/.codex/skills/henry-image/scripts/henry_image.py"
python3 "$script" generate --dry-run --route auto --candidate-policy auto --model gpt-image-2 --image-model gpt-image-2 --prompt "connectivity dry run" --out output/imagegen/dry-run.png
```

Expected signs:

- `provider.base_url_host` matches the dedicated router host.
- `metadata.base_url_source` is `HENRY_IMAGE_BASE_URL`, `HENRY_IMAGE_API_BASE`, or `HENRY_IMAGE_API_BASE_URL`.
- `metadata.auth_source` is `HENRY_IMAGE_API_KEY`, `HENRY_IMAGE_OPENAI_API_KEY`, or `HENRY_IMAGE_ACCESS_KEY`.
- `metadata.codex_access.mode` is `dedicated_henry_image_provider`.
- No secret value appears in stdout/stderr.

If the output shows `codex_config:*`, `127.0.0.1:25817`, `codex/router`, or `codex/by-provider`, the dedicated variables are not visible to the Codex process yet.
