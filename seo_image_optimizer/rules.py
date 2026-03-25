from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from PIL import Image, ImageOps, ImageStat

from .models import BatchInput, KeywordPool, ManifestRow


def build_keyword_pool(batch: BatchInput, website_summary: str = "") -> KeywordPool:
    genre_slug = _slug_words(batch.genre, fallback="portrait-photographer")
    city_words = _slug_words(batch.market_location, fallback="local-market")
    note_words = _slug_words(batch.notes, fallback="")
    service_phrases = _dedupe(
        [
            genre_slug,
            f"{genre_slug.split('-')[0]}-photographer" if "-" in genre_slug else genre_slug,
            "portrait-photographer",
            "branding-photographer" if "branding" in genre_slug else "",
            "headshot-photographer" if any(word in genre_slug for word in ("headshot", "branding", "business")) else "",
        ]
    )
    premium_modifiers = _dedupe(["luxury", "editorial", "bespoke", "refined", "premium"])
    plausible_locations = _dedupe(city_words.split("-") + [city_words, _domain_label(batch.website_url)])
    alt_text_style_notes = _dedupe(
        [
            "describe composition and orientation",
            "mention lighting or overall brightness when visually supported",
            "mention clean background or environmental setting only when clearly visible",
            note_words.replace("-", " "),
        ]
    )
    brand_summary = " ".join(
        part for part in [batch.studio_name, batch.genre, batch.market_location, batch.notes.strip()] if part
    )
    return KeywordPool(
        service_phrases=service_phrases[:5] or ["portrait-photographer"],
        premium_modifiers=premium_modifiers[:5],
        plausible_locations=plausible_locations[:6] or ["local-market"],
        alt_text_style_notes=alt_text_style_notes[:5],
        brand_summary=brand_summary,
    )


def generate_manifest_row(
    batch: BatchInput,
    keyword_pool: KeywordPool,
    image_path: Path,
    relative_path: str,
    existing_names: set[str],
) -> ManifestRow:
    analysis = analyze_image(image_path)
    filename = choose_filename(keyword_pool, analysis, existing_names)
    folder = "hero" if analysis["hero_candidate"] else "gallery"
    alt_text = build_alt_text(batch, analysis)
    return ManifestRow(
        source_path=relative_path.replace("\\", "/"),
        new_filename=filename,
        folder=folder,
        alt_text=alt_text,
    )


def analyze_image(image_path: Path) -> dict:
    with Image.open(image_path) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        width, height = image.size
        grayscale = image.convert("L")
        stat = ImageStat.Stat(grayscale)
        brightness = stat.mean[0]
        contrast = stat.stddev[0]
        orientation = "horizontal" if width > height else "vertical" if height > width else "square"
        brightness_label = (
            "bright" if brightness >= 180 else "light" if brightness >= 140 else "balanced" if brightness >= 95 else "moody"
        )
        contrast_label = "crisp" if contrast >= 65 else "soft" if contrast < 40 else "balanced"
        hero_candidate = orientation == "horizontal" and width >= 1800 and contrast >= 35
        return {
            "width": width,
            "height": height,
            "orientation": orientation,
            "brightness_label": brightness_label,
            "contrast_label": contrast_label,
            "hero_candidate": hero_candidate,
        }


def choose_filename(keyword_pool: KeywordPool, analysis: dict, existing_names: set[str]) -> str:
    service = keyword_pool.service_phrases[0]
    location = keyword_pool.plausible_locations[0]
    modifier = keyword_pool.premium_modifiers[0] if analysis["hero_candidate"] else ""
    setting = "studio" if analysis["orientation"] == "vertical" else "outdoor"
    patterns = [
        f"{location}-{service}.jpg",
        f"{service}-{location}.jpg",
        f"{modifier}-{service}-{location}.jpg" if modifier else "",
        f"{service}-{setting}-{location}.jpg",
    ]
    for candidate in patterns:
        clean = _sanitize_filename(candidate)
        if clean and clean not in existing_names:
            return clean
    for extra_location in keyword_pool.plausible_locations[1:]:
        clean = _sanitize_filename(f"{service}-{extra_location}.jpg")
        if clean not in existing_names:
            return clean
    for modifier in keyword_pool.premium_modifiers[1:]:
        clean = _sanitize_filename(f"{modifier}-{service}-{location}.jpg")
        if clean not in existing_names:
            return clean
    raise ValueError("Could not create a unique filename in rules-only mode.")


def build_alt_text(batch: BatchInput, analysis: dict) -> str:
    genre_label = batch.genre.strip().lower() or "portrait"
    city_label = batch.market_location.strip()
    parts = [
        f"{analysis['orientation'].capitalize()} {genre_label} photograph",
        f"with a {analysis['contrast_label']} look",
        f"and {analysis['brightness_label']} overall lighting",
    ]
    if city_label:
        parts.append(f"prepared for {city_label} website use")
    sentence = " ".join(parts).replace("  ", " ").strip()
    return sentence[0].upper() + sentence[1:] + "."


def _slug_words(value: str, fallback: str) -> str:
    words = []
    for raw in value.lower().replace("&", " ").replace("/", " ").split():
        clean = "".join(ch for ch in raw if ch.isalpha() or ch == "-")
        if clean:
            words.append(clean)
    return "-".join(words[:4]) or fallback


def _domain_label(url: str) -> str:
    host = urlparse(url).netloc.lower()
    host = host.replace("www.", "")
    label = host.split(".")[0] if host else ""
    return _slug_words(label, fallback="")


def _sanitize_filename(value: str) -> str:
    stem = Path(value).stem.lower()
    stem = "".join(ch if ch.isalpha() or ch == "-" else "-" for ch in stem)
    while "--" in stem:
        stem = stem.replace("--", "-")
    stem = stem.strip("-")
    if not stem:
        return ""
    return f"{stem}.jpg"


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
