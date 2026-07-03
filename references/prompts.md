# Henry Image Prompt Recipes

## Package format

Use this format when real generation is unavailable or reusable prompts are requested:

```text
Use case: <slug>
Prompt: <generation prompt>
Negative prompt: <avoid list>
Recommended size: <WIDTHxHEIGHT>
Recommended ratio: <ratio>
Platform notes:
- Midjourney: <parameters>
- SDXL: <parameters>
- Flux: <parameters>
```

## Henry photoreal street portrait

```text
Use case: photorealistic-natural
Prompt: A candid lifestyle street photo of a young Asian man, black oversized T-shirt, light blue jeans, black sunglasses, holding a drink and sipping through a straw, standing on a quiet urban residential street. Background includes muted pink-gray apartment buildings, glass stairwell, plants, roadside railings, utility pole, street wires, and a bicycle. Eye-level view, medium full-body framing, slight wide-angle phone street photography feeling, natural soft daylight, low-saturation city colors, realistic skin texture, Korean city street mood, subtle film-like social media photo texture.
Negative prompt: low resolution, over-smoothed skin, plastic skin, deformed fingers, wrong hands, warped sunglasses, distorted cup, extra people, watermark, text, logo, overexposed, underexposed, strong HDR, anime, illustration, overly cinematic, twisted buildings.
Recommended size: 1024x1024
Recommended ratio: 1:1
```

## Henry product photo

```text
Use case: product-mockup
Prompt: A realistic product photo of <product>, clean composition, natural material texture, accurate shape, controlled studio lighting, neutral background, sharp subject edges, subtle grounded shadow, commercial catalog quality.
Negative prompt: warped product, fake logo, misspelled text, watermark, extra objects, plastic texture, overprocessed lighting.
Recommended size: 1536x1024 or 1024x1024
```

## Henry social cover

```text
Use case: ads-marketing
Prompt: A polished social media cover image about <topic>, clear main visual hierarchy, strong focal subject, realistic or editorial visual style, enough negative space for later text placement, clean modern composition.
Negative prompt: embedded text, watermark, cluttered layout, illegible details, distorted faces, low resolution.
Recommended size: 1536x1024
```

## Henry transparent cutout

For simple opaque subjects:

```text
Create <subject> on a perfectly flat solid #00ff00 chroma-key background for background removal. The background must be one uniform color with no shadows, gradients, texture, reflections, floor plane, or lighting variation. Keep the subject fully separated from the background with crisp edges and generous padding. Do not use #00ff00 anywhere in the subject. No cast shadow, no contact shadow, no reflection, no watermark, and no text unless explicitly requested.
```

For hair, glass, smoke, liquids, reflections, or soft shadows, prefer true transparent output only when the active route supports it.

## Henry identity-preserving edit

```text
Use case: identity-preserve
Prompt: Use the input image as the identity and pose reference. Keep the same person, face structure, body proportions, pose, and clothing silhouette. Change only <target change>. Match lighting, perspective, camera angle, and skin texture. Do not add extra people or text.
Negative prompt: identity drift, changed face, changed pose, distorted hands, unrealistic skin, watermark, text, logo.
```

## Henry reference-style generation

```text
Use case: style-transfer
Prompt: Use the input image as style and composition reference only. Generate <new subject> with similar framing, lighting, color mood, and texture. Do not copy any logo, text, brand mark, or unique private detail from the reference.
Negative prompt: copied text, copied logo, watermark, distorted subject, low resolution.
```

## Batch JSONL examples

```jsonl
{"prompt":"A candid city street portrait, soft overcast light, no text","size":"1024x1024","quality":"medium","out":"output/imagegen/henry-street-1.png"}
{"prompt":"A clean product photo of a matte ceramic mug","size":"1536x1024","quality":"medium","out":"output/imagegen/henry-mug-1.png"}
```
