# Henry Image Quality Review

Start with `workflow-map.md` for the full flow. This page only owns the review and stop/retry decision.

Review generated image outputs before claiming success or deciding on another iteration.

## Review Checklist

Check:

- subject correctness;
- style and medium match;
- composition and aspect ratio match;
- input image role was followed;
- feedback annotations, red boxes, UI chrome, or correction text were not copied;
- visible text is correct and readable if text was requested;
- dimensions and labels are plausible if present;
- multiple views agree with each other;
- hidden structure stays hidden when sealed;
- transparent or cutout requirements are satisfied;
- no watermark, random logo, severe artifact, or low quality.

## Retry Policy

```text
ordinary visual issue -> retry once with a targeted correction
text, dimension, or engineering issue -> retry at most twice
repeated structural failure -> switch to SVG/PDF/OpenSCAD/spec
API or route failure -> use checked CLI fallback within authorized routes; return prompt package only after real image bytes cannot be produced or Henry asked for prompt-only output
```

## Targeted Correction Pattern

Use this pattern for one retry:

```text
Keep: <accepted parts>
Fix only: <specific defect>
Do not change: <invariants>
Avoid: <failure pattern>
```

Do not stack unrelated new creative changes into a retry.

## Stop Conditions

Stop raster iteration when:

- exact dimensions keep changing;
- top/front/side views disagree;
- generated text remains wrong;
- annotated feedback keeps appearing in the output;
- internal structure appears when the product should be sealed;
- the request is really a manufacturing/CAD/spec task.

Then produce or recommend deterministic SVG/PDF/OpenSCAD/spec output.
