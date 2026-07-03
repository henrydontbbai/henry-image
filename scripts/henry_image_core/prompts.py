from __future__ import annotations

from typing import Any


def casual_traits(prompt: str) -> set[str]:
    traits: set[str] = set()
    if "高级" in prompt:
        traits.add("premium")
    if "别太假" in prompt or "不要太假" in prompt or "真实" in prompt:
        traits.add("realistic")
    return traits


def infer_use_case(prompt: str, explicit_use_case: str | None) -> str:
    value = (explicit_use_case or "").strip()
    if value and value not in {"photorealistic-natural", "auto"}:
        return value
    lowered = prompt.lower()
    if any(token in prompt for token in ("3D 打印", "3d 打印", "CAD", "尺寸", "支架", "图纸", "工程图", "三视图")):
        return "engineering-concept"
    if any(token in prompt for token in ("透明", "抠图", "去背景", "透明背景")):
        return "transparent-cutout"
    if any(token in prompt for token in ("小红书", "封面", "封图", "首图")):
        return "social-cover"
    if any(token in prompt for token in ("产品图", "商品图", "产品渲染")):
        return "product-render"
    if any(token in prompt for token in ("头像", "profile", "avatar")):
        return "avatar"
    if any(token in prompt for token in ("海报", "poster")):
        return "poster"
    if any(token in prompt for token in ("logo", "标志", "品牌标识")):
        return "logo-concept"
    if any(token in prompt for token in ("UI", "界面", "mockup", "线框图")):
        return "UI/mockup"
    if any(token in prompt for token in ("信息图", "infographic", "图解")):
        return "infographic"
    if any(token in prompt for token in ("改图", "修改", "换背景", "修图", "编辑")):
        return "image-edit"
    if "batch" in lowered or "批量" in prompt:
        return "batch-variants"
    return "photo-realistic"


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
    hard_constraints = ["do not invent brand names, logos, dimensions, or exact text"]
    validation_checklist = ["subject matches request", "style matches requested use case", "no watermark or random logo", "no low-quality artifacts"]

    if "premium" in traits:
        style = "premium, restrained, polished, realistic"
        composition = "uncluttered composition with deliberate negative space"
        lighting = "controlled studio lighting"
        color_material = "premium material feel, realistic surfaces, non-plastic unless requested"
        assumptions.append("高级 -> premium restrained composition and controlled lighting")
    if "realistic" in traits:
        style = "realistic with natural texture and plausible lighting"
        color_material = "non-plastic surfaces, realistic texture"
        assumptions.append("别太假 -> realistic texture and plausible light")

    if use_case == "product-render":
        output_intent = "clean product render"
        scene = "simple controlled backdrop"
        composition = "centered product, subtle grounded shadow, usable negative space"
        lighting = "soft controlled studio lighting"
        color_material = "accurate product shape and realistic material texture"
        validation_checklist.extend(["product shape is plausible", "no invented logo or text"])
    elif use_case == "social-cover":
        output_intent = "social media cover image"
        scene = "clean editorial/social cover layout"
        composition = "strong focal subject, bright clean composition, usable negative space"
        lighting = "bright but natural light"
        color_material = "fresh, readable, platform-friendly colors"
        validation_checklist.extend(["cover has clear focal hierarchy", "no random embedded text"])
        assumptions.append("小红书封面 -> social-cover layout with negative space")
    elif use_case == "avatar":
        output_intent = "avatar image"
        scene = "simple clean background"
        composition = "centered face or character, clear silhouette"
        validation_checklist.extend(["avatar reads clearly at small size", "face/character is not distorted"])
    elif use_case == "transparent-cutout":
        output_intent = "transparent or cutout-ready asset"
        scene = "flat removable background or transparent-output route when available"
        composition = "single isolated subject with generous padding"
        hard_constraints.append("keep subject separated from background with crisp edges")
        validation_checklist.extend(["background is removable", "subject edges are clean"])
    elif use_case == "engineering-concept":
        output_intent = "engineering concept or vendor communication asset"
        scene = "clean technical presentation background"
        style = "clear technical concept render or deterministic diagram"
        composition = "front/side/top information should be consistent"
        lighting = "neutral product lighting"
        hard_constraints.append("deterministic output warning: raster output is concept-only; final manufacturing needs SVG/PDF/OpenSCAD/spec")
        validation_checklist.extend(["dimensions are not trusted from pixels", "multi-view geometry is consistent", "switch to deterministic output if structure fails"])
        assumptions.append("engineering keywords -> deterministic output warning included")
    elif use_case == "logo-concept":
        output_intent = "logo concept exploration"
        scene = "plain background"
        style = "simple, vector-friendly mark concept"
        composition = "centered mark with clear silhouette"
        hard_constraints.append("do not copy existing brand marks")
        validation_checklist.extend(["mark is simple", "no copied brand identity"])

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
        "execution_route": "built-in image_gen when available; Henry CLI for local output/manifest/probe/batch; prompt package fallback when generation is unavailable",
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
    width_height = parse_size(size)
    platforms: dict[str, Any] = {
        "openai": {
            "prompt": canonical,
            "notes": "Use with built-in image_gen or Responses image_generation.",
        },
        "flux": {
            "prompt": f"{compiled_task['subject']}, {compiled_task['style']}, {compiled_task['composition']}, high quality",
            "negative_prompt": negative_prompt,
            "parameters": "guidance 3.5-5, 20-30 steps",
        },
        "sdxl": {
            "positive": canonical,
            "negative": negative_prompt,
            "parameters": "CFG 5-7, 25-35 steps, DPM++ 2M Karras",
        },
        "midjourney": {
            "prompt": f"{canonical} --ar {ratio} --style raw --stylize 50 --quality 1",
        },
        "comfyui": {
            "positive_prompt": canonical,
            "negative_prompt": negative_prompt,
            "width": width_height[0] if width_height else 1024,
            "height": width_height[1] if width_height else 1024,
            "seed": "random",
            "note": "Slot map only; ComfyUI is not called in this phase.",
        },
    }
    selected = platforms if platform == "all" else {platform: platforms[platform]}
    return {
        "version": 2,
        "original_prompt": original_prompt,
        "compiled_task": {k: v for k, v in compiled_task.items() if k != "canonical_prompt"},
        "recommended_size": size,
        "recommended_ratio": ratio,
        "platforms": selected,
        "validation_checklist": compiled_task["validation_checklist"],
        "assumptions": compiled_task["assumptions"],
    }
