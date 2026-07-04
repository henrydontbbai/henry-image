# Quick Card

## Dry run

```powershell
python .\scripts\henry_image.py generate `
  --dry-run `
  --route auto `
  --model response-model-v1 `
  --image-model image-model-v1 `
  --prompt "Connectivity dry run" `
  --out "output\imagegen\dry-run.png"
```

## Generate

```powershell
python .\scripts\henry_image.py generate `
  --route responses `
  --model response-model-v1 `
  --image-model image-model-v1 `
  --prompt "A clean product photo of a ceramic cup" `
  --out "output\imagegen\cup.png" `
  --force
```

## Edit

```powershell
python .\scripts\henry_image.py edit `
  --route auto `
  --model response-model-v1 `
  --image-model image-model-v1 `
  --image ".\input\source.png" `
  --prompt "Replace the background with a soft studio setup" `
  --out "output\imagegen\edit.png" `
  --force
```

## Probe

```powershell
python .\scripts\henry_image.py probe `
  --route auto `
  --model response-model-v1 `
  --image-model image-model-v1
```

## Batch

```powershell
python .\scripts\henry_image.py batch `
  --route auto `
  --model response-model-v1 `
  --image-model image-model-v1 `
  --batch-input ".\input\tasks.jsonl" `
  --out-dir "output\imagegen\batch"
```

## Job Recovery

```powershell
python .\scripts\henry_image.py job-status --job ".\output\imagegen\jobs\job-123"
python .\scripts\henry_image.py job-diagnose --job ".\output\imagegen\jobs\job-123" --format human
python .\scripts\henry_image.py job-list
```
