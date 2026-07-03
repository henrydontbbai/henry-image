# Henry Image Input Roles

Before using any image input, state its role. This prevents annotated screenshots, rough sketches, and previous failed generations from being treated as final content.

## Roles

- `edit target`: the image to modify while preserving unchanged parts.
- `visual reference`: borrow composition, object type, or layout only.
- `style reference`: borrow visual style, lighting, texture, or mood only.
- `dimensional sketch`: use structure idea only; dimensions from text/spec override pixels.
- `feedback annotation`: extract requested changes; do not reproduce red marks, comments, UI chrome, or arrows.
- `previous output`: correct listed defects and preserve accepted parts.
- `negative example`: avoid the shown defect, structure, or style.

## Annotated Screenshots

Treat red boxes, handwritten notes, arrows, UI overlays, app chrome, and correction text as instructions.

Before prompting, convert the annotation into a concise change list:

```text
Input image role: feedback annotation.
Keep: accepted design features.
Change: listed correction points.
Remove from final: red boxes, handwritten notes, UI chrome, correction text.
```

Do not send an annotated screenshot to an image model as an edit target unless the final output should preserve the base image itself.

## Dimension Sketches

For rough sketches with numbers:

- use the sketch for intent and layout;
- use explicit text dimensions as authoritative;
- identify unclear or conflicting dimensions before generating;
- do not infer manufacturing tolerances from pixels.

## Previous Outputs

For iterative corrections:

- list accepted parts;
- list defects to fix;
- restate hard constraints;
- avoid adding new design changes not requested in the correction.
