# Henry Image Prompt Packages

Use prompt packages only when Henry explicitly wants reusable prompts for another platform, or after a checked Henry CLI generation/edit attempt cannot produce real image bytes. Router uncertainty alone is not enough: for normal `gpt-image-2`, first run the CLI dry-run/probe or generation path.

## Package Structure

`henry_image.py prompt` supports two package versions:

- v1: legacy shape, default for backward compatibility.
- v2: compiled task, platform prompts, assumptions, and validation checklist.

Prompt package v2 should include the original user request, the compiled task from `prompt-compiler.md`, platform prompts, negative prompt, and validation checklist.

Return a package with platform-specific sections:

```text
Use case: <slug>
Original request: <raw user request>
Compiled task:
  Output intent: <intent>
  Subject: <subject>
  Scene: <scene>
  Style: <style>
  Composition: <composition>
  Lighting: <lighting>
  Color/material: <color/material>
  Text requirements: <exact text or no generated text>
  Input image roles: <roles>
  Hard constraints: <constraints>
Primary prompt: <canonical prompt>
Avoid: <negative prompt>
Recommended size: <WIDTHxHEIGHT>
Recommended ratio: <ratio>

OpenAI / gpt-image reusable prompt:
<prompt emphasizing subject, composition, invariants, and edit constraints>

Flux:
<short positive prompt with style and composition tags>
Guidance: 3.5-5
Steps: 20-30

SDXL:
Positive: <prompt>
Negative: <negative prompt>
CFG: 5-7
Steps: 25-35
Sampler: DPM++ 2M Karras

ComfyUI slot map:
positive_prompt: <prompt>
negative_prompt: <negative prompt>
width: <width>
height: <height>
seed: random or fixed by user

Validation checklist:
<short output review checklist>
```

## Prompt Package Rules

- Do not include secrets, base64 image data, or private file contents.
- For edit tasks, list invariants explicitly.
- For annotated screenshots, describe the extracted correction list and exclude annotation marks.
- For engineering diagrams, state whether raster output is only a concept preview.
- If dimensions are involved, put dimensions in a separate spec block so another tool or vendor can reuse them.
- For vague requests, include assumptions made by the understanding layer.
- For platform prompts, do not imply that non-OpenAI backends are available in this phase; they are reusable prompt outputs only.

## CLI Version Behavior

Legacy command:

```bash
python3 scripts/henry_image.py prompt --prompt "画个高级产品图"
```

returns `type: henry_prompt_package`.

Compiled command:

```bash
python3 scripts/henry_image.py prompt --prompt "画个高级产品图" --package-version 2 --explain
```

returns `type: henry_prompt_package_v2` with `compiled_task`, `platforms`, `validation_checklist`, and `assumptions`.

## Engineering Prompt Package Addendum

When a raster concept image is still useful for a dimension-critical task, add:

```text
Engineering note:
This prompt is for a visual concept only. Final manufacturing should use the accompanying dimensions/spec/CAD output, not generated pixels.
```
