# Setup

## Required variables

```text
HENRY_IMAGE_BASE_URL
HENRY_IMAGE_API_KEY
HENRY_IMAGE_MODEL
HENRY_IMAGE_IMAGE_MODEL
```

## Recommended order

1. set the variables in the local environment
2. start a new terminal or app session that can see them
3. use `probe` for a readiness check or `generate --dry-run` for a command preview

## Dry run example

```powershell
python .\scripts\henry_image.py generate `
  --dry-run `
  --route auto `
  --model response-model-v1 `
  --image-model image-model-v1 `
  --prompt "Connectivity dry run" `
  --out "output\imagegen\dry-run.png"
```

## Probe example

```powershell
python .\scripts\henry_image.py probe `
  --route auto `
  --model response-model-v1 `
  --image-model image-model-v1
```

## Expected result

The output should show the selected route and the sources for:

- `base_url_source`
- `auth_source`

Use `probe` when you do not need an output file. Use `generate --dry-run` when you want a replayable command preview for a real image run.
