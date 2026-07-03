# Henry Image Prompt Compiler

The prompt compiler turns natural language into a structured, platform-ready image task. Use it before CLI generation/editing, explicit prompt packaging, or manual fallback.

## Canonical Prompt Schema

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

## Compile Rules

- Preserve the user's subject and requested changes.
- Convert casual style words into concrete visual constraints using `understanding.md`.
- Keep exact visible text empty unless Henry provided it verbatim.
- Put dimensions and manufacturing requirements in `Hard constraints`, not only in prose.
- Put image roles in `Input image roles` before editing or reference use.
- Add negative constraints that prevent common failures for the chosen use case.
- Select route after compiling: Henry CLI for image-output requests, deterministic engineering output for CAD-like work, or prompt package only for explicit prompt-only requests / checked CLI failure. Do not choose built-in `image_gen`, Flux, or prompt package as the default for Henry Image generation.

## Platform Outputs

Prompt package v2 should contain:

- `openai_image_gen_prompt`: natural language prompt optimized for Henry CLI Responses `image_generation` and reusable prompt-only output.
- `flux_prompt`: concise prompt with subject, style, composition, and quality tags.
- `sdxl_positive`: detailed positive prompt.
- `sdxl_negative`: explicit negative prompt.
- `midjourney_prompt`: compact descriptive prompt with aspect ratio hints.
- `comfyui_slot_map`: prompt fields for future workflow adapters only; do not call ComfyUI in this phase.
- `validation_checklist`: short list used to review the output.

## Example

Raw request:

```text
画个高级点的产品图
```

Compiled task:

```text
Use case: product-render
Output intent: general high-quality preview image
Subject: product unspecified; ask if product is not discoverable from context
Scene: clean studio background
Style: realistic premium product render
Composition: centered product, subtle shadow, uncluttered negative space
Lighting: soft controlled studio light
Color/material: realistic material texture, non-plastic unless requested
Text requirements: no generated text
Input image roles: none
Hard constraints: do not invent brand or logo
Negative constraints: no watermark, no logo, no illegible text, no distorted object, no low quality
Execution route: Henry CLI generate with --route responses --candidate-policy auto --model gpt-image-2 --image-model gpt-image-2; prompt package only if explicitly requested or after checked CLI failure
Validation checklist: product shape plausible; premium feel; no random logo/text; clean composition
```
