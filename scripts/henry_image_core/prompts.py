from __future__ import annotations

from typing import Any


def casual_traits(prompt: str) -> set[str]:
    lowered = prompt.lower()
    traits: set[str] = set()
    if "premium" in lowered or "high-end" in lowered:
        traits.add("premium")
    if "realistic" in lowered or "natural" in lowered:
        traits.add("realistic")
    return traits


def infer_use_case(prompt: str, explicit_use_case: str | None) -> str:
    value = (explicit_use_case or "").strip()
    if value and value not in {"auto", "generic"}:
        return value
    lowered = prompt.lower()
    if any(token in lowered for token in ("technical", "engineering", "dimension", "diagram")):
        return "engineering-concept"
    if any(token in lowered for token in ("transparent", "cutout", "cut-out")):
        return "transparent-cutout"
    if any(token in lowered for token in ("cover", "social", "banner")):
        return "social-cover"
    if any(token in lowered for token in ("product", "render")):
        return "product-render"
    if "avatar" in lowered or "profile" in lowered:
        return "avatar"
    if "poster" in lowered:
        return "poster"
    if "logo" in lowered:
        return "logo-concept"
    if "mockup" in lowered or "ui" in prompt:
        return "UI/mockup"
    if "infographic" in lowered:
        return "infographic"
    if "edit" in lowered or "replace background" in lowered:
        return "image-edit"
    if "batch" in lowered:
        return "batch-variants"
    return "generic-image"


def ratio_from_size(size: str, parse_size: Any) -> str:
    parsed = parse_size(size)
    if parsed is None:
        return "1:1"
    width, height = parsed
    if width == height:
        return "1:1"
    if width > height and abs((width / height) - 1.5) < 0.05:
        return "3:2"
    if height > width and abs((height / width) - 1.5) < 0.05:
        return "2:3"
    return f"{width}:{height}"


def compile_prompt_task(
    *,
    prompt: str,
    explicit_use_case: str | None,
    size: str,
    negative_prompt: str,
    review_template: str,
) -> dict[str, Any]:
    use_case = infer_use_case(prompt, explicit_use_case)
    assumptions = ["ratio unknown -> using requested/default size " + size]
    traits = casual_traits(prompt)
    subject = prompt
    output_intent = "general high-quality preview image"
    scene = "clean, uncluttered setting"
    style = "realistic, clean, natural light"
    composition = "clear main subject, balanced composition"
    lighting = "soft controlled light"
    color_material = "natural colors and realistic material texture"
    text_requirements = "no generated text unless explicitly requested"
    input_image_roles = "none"
    hard_constraints = ["do not invent logos, measurements, or exact text"]
    validation_checklist = ["subject matches request", "style matches requested use case", "no watermark or random logo", "no low-quality artifacts"]

    if "premium" in traits:
        style = "premium, restrained, polished, realistic"
        composition = "uncluttered composition with deliberate negative space"
        lighting = "controlled studio lighting"
        color_material = "premium material feel, realistic surfaces"
        assumptions.append("premium wording -> restrained composition and controlled lighting")
    if "realistic" in traits:
        style = "realistic with natural texture and plausible lighting"
        color_material = "non-plastic surfaces, realistic texture"
        assumptions.append("realistic wording -> plausible light and texture")

    if use_case == "product-render":
        output_intent = "clean product render"
        scene = "simple controlled backdrop"
        composition = "centered product with usable negative space"
        lighting = "soft controlled studio lighting"
        color_material = "accurate product shape and realistic material texture"
    elif use_case == "social-cover":
        output_intent = "social cover image"
        scene = "clean editorial layout"
        composition = "strong focal subject with usable negative space"
        lighting = "bright but natural light"
        color_material = "fresh, readable colors"
        assumptions.append("cover wording -> social layout with negative space")
    elif use_case == "avatar":
        output_intent = "avatar image"
        scene = "simple clean background"
        composition = "centered face or character with a clear silhouette"
    elif use_case == "transparent-cutout":
        output_intent = "cutout-ready asset"
        scene = "flat removable background"
        composition = "single isolated subject with generous padding"
        hard_constraints.append("keep subject separated from background with crisp edges")
    elif use_case == "engineering-concept":
        output_intent = "engineering concept asset"
        scene = "clean technical presentation background"
        style = "clear technical concept render or deterministic diagram"
        composition = "front, side, and top information should remain consistent"
        lighting = "neutral product lighting"
        hard_constraints.append("raster output is concept-only; final manufacturing should use a deterministic vector or specification format")
        validation_checklist.extend(["dimensions are not trusted from pixels", "multi-view geometry is consistent"])
        assumptions.append("engineering wording -> deterministic output warning included")
    elif use_case == "logo-concept":
        output_intent = "logo concept exploration"
        scene = "plain background"
        style = "simple mark concept"
        composition = "centered mark with clear silhouette"
        hard_constraints.append("do not copy an existing brand mark")

    if review_template != "auto":
        assumptions.append("review template forced -> " + review_template)

    canonical_prompt = (
        f"{output_intent}. Subject: {subject}. Scene: {scene}. Style: {style}. "
        f"Composition: {composition}. Lighting: {lighting}. Color/material: {color_material}. "
        f"Text: {text_requirements}. Hard constraints: {'; '.join(hard_constraints)}."
    )
    return {
        "use_case": use_case,
        "output_intent": output_intent,
        "subject": subject,
        "scene": scene,
        "style": style,
        "composition": composition,
        "lighting": lighting,
        "color_material": color_material,
        "text_requirements": text_requirements,
        "input_image_roles": input_image_roles,
        "hard_constraints": hard_constraints,
        "negative_constraints": negative_prompt,
        "execution_route": "Henry Image generate, edit, batch, or a prompt package when image delivery is not requested",
        "validation_checklist": validation_checklist,
        "assumptions": assumptions,
        "canonical_prompt": canonical_prompt,
    }


def build_prompt_package_v2(
    *,
    original_prompt: str,
    compiled_task: dict[str, Any],
    size: str,
    negative_prompt: str,
    platform: str,
    parse_size: Any,
) -> dict[str, Any]:
    ratio = ratio_from_size(size, parse_size)
    canonical = compiled_task["canonical_prompt"]
    return {
        "version": 1,
        "original_prompt": original_prompt,
        "compiled_task": {k: v for k, v in compiled_task.items() if k != "canonical_prompt"},
        "recommended_size": size,
        "recommended_ratio": ratio,
        "negative_prompt": negative_prompt,
        "prompt": canonical,
        "usage": "Use this package with a Henry Image-compatible remote image service.",
        "validation_checklist": compiled_task["validation_checklist"],
        "assumptions": compiled_task["assumptions"],
    }
