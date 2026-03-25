from __future__ import annotations

import base64
import io
import json
import re
from pathlib import Path

from openai import OpenAI
from PIL import Image, ImageOps

from .models import BatchInput, KeywordPool, ManifestRow


def _client(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key)


def build_keyword_pool(batch: BatchInput, website_summary: str) -> KeywordPool:
    prompt = f"""
You are building a keyword pool for a photographer SEO image delivery workflow.

Studio name: {batch.studio_name}
Website: {batch.website_url}
Genre: {batch.genre}
Primary market location: {batch.market_location}
Business address: {batch.business_address}
Extra notes: {batch.notes or "None"}

Website summary:
{website_summary[:14000]}

Return JSON with this schema:
{{
  "service_phrases": ["..."],
  "premium_modifiers": ["..."],
  "plausible_locations": ["..."],
  "alt_text_style_notes": ["..."],
  "brand_summary": "..."
}}

Rules:
- service_phrases should be search-intent phrases such as headshot-photographer
- premium_modifiers should be tasteful and selective
- plausible_locations should stay realistic to the stated market
- alt_text_style_notes should push more descriptive but still truthful alt text
- keep each list to 5-8 items
- return JSON only
""".strip()

    response = _client(batch.openai_api_key).responses.create(
        model=batch.openai_model,
        input=prompt,
        temperature=0.3,
    )
    data = _extract_json(response.output_text)
    return KeywordPool(**data)


def generate_manifest_row(
    batch: BatchInput,
    keyword_pool: KeywordPool,
    image_path: Path,
    relative_path: str,
    existing_names: set[str],
) -> ManifestRow:
    image_b64 = base64.b64encode(_encode_for_vision(image_path)).decode("utf-8")
    prompt = f"""
Create one manifest row for an SEO image optimizer.

Studio name: {batch.studio_name}
Genre: {batch.genre}
Primary market location: {batch.market_location}
Business address: {batch.business_address}
Brand summary: {keyword_pool.brand_summary}
Approved service phrases: {json.dumps(keyword_pool.service_phrases)}
Approved premium modifiers: {json.dumps(keyword_pool.premium_modifiers)}
Approved plausible locations: {json.dumps(keyword_pool.plausible_locations)}
Alt text style notes: {json.dumps(keyword_pool.alt_text_style_notes)}
Existing filenames already used in this batch: {json.dumps(sorted(existing_names))}

Return JSON only with:
{{
  "new_filename": "filename.jpg",
  "folder": "hero or gallery",
  "alt_text": "descriptive alt text"
}}

Rules:
- filename must be lowercase with hyphens only
- no digits anywhere in filename
- filename must sound commercially credible for search intent
- alt text must be more descriptive than basic alt text but still strictly truthful to the visible image
- alt text should mention composition, clothing, setting, pose, lighting, or background when clearly visible
- include at most one natural keyword or location phrase
- hero should be reserved for only the strongest homepage-worthy images
- return JSON only
""".strip()

    response = _client(batch.openai_api_key).responses.create(
        model=batch.openai_model,
        input=[
            {"role": "user", "content": [{"type": "input_text", "text": prompt}]},
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_image",
                        "image_url": f"data:image/jpeg;base64,{image_b64}",
                        "detail": "low",
                    }
                ],
            },
        ],
        temperature=0.5,
    )
    data = _extract_json(response.output_text)
    filename = sanitize_filename(data["new_filename"])
    folder = "hero" if data.get("folder") == "hero" else "gallery"
    alt_text = sanitize_alt_text(data["alt_text"])
    filename = ensure_unique_filename(filename, existing_names, keyword_pool)
    return ManifestRow(
        source_path=relative_path.replace("\\", "/"),
        new_filename=filename,
        folder=folder,
        alt_text=alt_text,
    )


def sanitize_filename(value: str) -> str:
    suffix = Path(value).suffix.lower() or ".jpg"
    stem = Path(value).stem.lower()
    stem = re.sub(r"[^a-z-]+", "-", stem)
    stem = re.sub(r"-{2,}", "-", stem).strip("-")
    stem = re.sub(r"\d+", "", stem)
    stem = re.sub(r"-{2,}", "-", stem).strip("-")
    if not stem:
        stem = "portrait-photographer"
    return f"{stem}{suffix}"


def sanitize_alt_text(value: str) -> str:
    text = " ".join(value.split())
    return text[:300]


def ensure_unique_filename(filename: str, existing_names: set[str], keyword_pool: KeywordPool) -> str:
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    if filename not in existing_names:
        return filename

    variants: list[str] = []
    for modifier in keyword_pool.premium_modifiers:
        variants.append(f"{modifier}-{stem}{suffix}")
    for location in keyword_pool.plausible_locations:
        variants.append(f"{stem}-{location}{suffix}")
    for service in keyword_pool.service_phrases:
        variants.append(f"{service}-{stem}{suffix}")

    for variant in variants:
        clean = sanitize_filename(variant)
        if clean not in existing_names:
            return clean
    fallback = sanitize_filename(f"editorial-{stem}{suffix}")
    if fallback not in existing_names:
        return fallback
    raise ValueError("Could not create a unique filename without digits.")


def _extract_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def _encode_for_vision(image_path: Path) -> bytes:
    with Image.open(image_path) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=88)
        return buffer.getvalue()
