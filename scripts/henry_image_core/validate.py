from __future__ import annotations

from pathlib import Path
import re
from typing import Any


def read_prompt(prompt: str | None, prompt_file: str | None) -> str:
    if prompt and prompt_file:
        raise ValueError("Use --prompt or --prompt-file, not both.")
    if prompt_file:
        path = Path(prompt_file)
        if not path.exists():
            raise ValueError(f"Prompt file not found: {path}")
        text = path.read_text(encoding="utf-8").strip()
    elif prompt:
        text = prompt.strip()
    else:
        raise ValueError("Missing prompt. Use --prompt or --prompt-file.")
    if not text:
        raise ValueError("Prompt is empty.")
    return text


def parse_size(size: str) -> tuple[int, int] | None:
    if size == "auto":
        return None
    match = re.fullmatch(r"([1-9][0-9]*)x([1-9][0-9]*)", size)
    if not match:
        raise ValueError("size must be auto or WIDTHxHEIGHT, for example 1024x1024.")
    return int(match.group(1)), int(match.group(2))


def validate_common(
    args: Any,
    *,
    qualities: set[str],
    output_formats: set[str],
    image_response_formats: set[str],
    routes: set[str],
) -> None:
    parsed_size = parse_size(args.size)
    if parsed_size is not None:
        width, height = parsed_size
        if width > 3840 or height > 3840:
            raise ValueError("size width and height must be <= 3840.")
        if width * height > 8_294_400:
            raise ValueError("size total pixels must be <= 8,294,400.")
    if args.quality not in qualities:
        raise ValueError("quality must be one of low, medium, high, standard, hd, or auto.")
    if args.output_format not in output_formats:
        raise ValueError("output-format must be png, jpeg, or webp.")
    if args.images_response_format not in image_response_formats:
        raise ValueError("images-response-format must be auto, b64_json, or url.")
    if args.route not in routes:
        raise ValueError("route must be one of auto, responses, or images.")
    if args.n < 1 or args.n > 10:
        raise ValueError("n must be between 1 and 10.")
    if args.timeout < 1:
        raise ValueError("timeout must be at least 1 second.")
    if args.output_compression is not None:
        if args.output_format == "png":
            raise ValueError("output-compression only applies to jpeg or webp.")
        if args.output_compression < 0 or args.output_compression > 100:
            raise ValueError("output-compression must be between 0 and 100.")
