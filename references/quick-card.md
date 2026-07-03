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
