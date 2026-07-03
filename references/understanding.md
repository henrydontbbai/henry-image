# Henry Image Prompt Understanding

Start with `workflow-map.md` for the overall path. This page only owns the understanding step.

This document defines the universal understanding layer for vague, short, mixed-language, or casual image requests. The goal is to turn any reasonable user description into a clear image task before choosing a generation route.

## Understanding Pipeline

```text
raw user description
-> identify image type
-> extract subject, scene, style, composition, size, usage, constraints
-> classify input image roles
-> safely fill missing details
-> detect conflicts or missing high-impact intent
-> choose execution route
-> execute CLI generate/edit for image-output requests; use prompt package only for explicit prompt-only requests or checked CLI failure
-> review output
-> retry with a targeted correction or switch output form
```

## Image Type Enum

Use one primary type:

- `photo-realistic`
- `product-render`
- `social-cover`
- `poster`
- `avatar`
- `logo-concept`
- `UI/mockup`
- `infographic`
- `engineering-concept`
- `transparent-cutout`
- `image-edit`
- `reference-to-image`
- `batch-variants`

## Default Completion Strategy

Apply these defaults when they do not change the user's intent:

```text
subject clear -> keep the subject unchanged
usage unknown -> general high-quality preview image
ratio unknown -> 1024x1024
style unknown -> realistic, clean, natural light
text unknown -> no generated text
negative defaults -> no watermark, no logo, no illegible text, no distorted anatomy, no low quality
```

## Casual Language Mapping

Convert vague words into concrete visual constraints:

- "高级" -> restrained composition, premium material feel, controlled lighting, uncluttered background.
- "别太假" -> natural texture, realistic proportions, non-plastic surfaces, plausible lighting.
- "小红书感" -> clean social cover composition, strong subject, bright but natural color, usable negative space.
- "电影感" -> cinematic composition, motivated lighting, atmospheric contrast, realistic lens feel.
- "产品图" -> accurate product shape, studio lighting, subtle shadow, clean background.
- "示意图" -> clear structure, sparse labels, readable layout, no decorative clutter.

## Safe Completion Boundaries

Safe to add:

- composition and framing hints;
- lighting and material detail;
- quality and clarity constraints;
- negative constraints;
- platform-neutral prompt structure.

Do not invent:

- brand names, slogans, or copyrighted marks;
- identity, age, ethnicity, or personal traits not requested;
- exact text content;
- product dimensions or engineering tolerances;
- extra characters or objects that change the concept.

## Conflict Handling

Normalize minor conflicts when the intended result is clear:

- "极简但信息清楚" -> minimal layout with only essential elements.
- "真实照片但有一点插画感" -> realistic base with subtle stylized softness.

Ask or stop for high-impact conflicts:

- exact text is requested but text content is missing;
- subject is unclear;
- edit target vs reference role is ambiguous;
- dimensions conflict with provided specs;
- "real photo" and "cartoon logo" are both central requirements;
- safety, legality, or credential issues appear.

## When To Ask Henry

Ask only when the missing answer materially changes output:

- primary subject;
- target use case;
- exact visible text;
- aspect ratio for a production asset;
- edit target vs reference image role;
- engineering dimensions or tolerances.

Otherwise proceed with defaults and record assumptions in the CLI prompt/manifest response, or in a prompt package only when prompt-only output is requested.
