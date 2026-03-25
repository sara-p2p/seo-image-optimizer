from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image, ImageFilter, ImageOps, ImageStat

from .models import BatchInput, KeywordPool, ManifestRow


def build_keyword_pool(batch: BatchInput, website_summary: str = "") -> KeywordPool:
    genre_slug = _slug_words(batch.genre, fallback="portrait")
    service_slug = _slug_words(batch.service_type, fallback="photographer")
    city_slug = _slug_words(batch.market_location, fallback="local-market")
    website_terms = _extract_site_terms(website_summary)
    modifier_pool = _brand_modifiers(batch.brand_style)

    service_phrases = _dedupe(
        [
            f"{genre_slug}-{service_slug}",
            f"{service_slug}-{genre_slug}" if service_slug != genre_slug else "",
            f"{genre_slug}-photographer",
            f"{service_slug}-photographer",
            "portrait-photographer",
            website_terms[0] if website_terms else "",
        ]
    )
    locations = _dedupe(city_slug.split("-") + [city_slug, _domain_label(batch.website_url)] + website_terms[1:3])
    style_notes = _dedupe(
        [
            "describe crop feel and subject placement",
            "mention lighting strength and direction when visually supported",
            "mention clean background or layered environment only when clearly visible",
            batch.notes.strip().lower(),
        ]
    )
    return KeywordPool(
        service_phrases=service_phrases[:6] or ["portrait-photographer"],
        premium_modifiers=modifier_pool[:5],
        plausible_locations=locations[:6] or ["local-market"],
        alt_text_style_notes=style_notes[:5],
        brand_summary=" ".join(
            part
            for part in [
                batch.studio_name,
                batch.genre,
                batch.service_type,
                batch.brand_style,
                batch.market_location,
                batch.notes.strip(),
            ]
            if part
        ),
    )


def generate_manifest_row(
    batch: BatchInput,
    keyword_pool: KeywordPool,
    image_path: Path,
    relative_path: str,
    existing_names: set[str],
) -> ManifestRow:
    analysis = analyze_image(image_path)
    filename = choose_filename(batch, keyword_pool, analysis, existing_names)
    alt_text = build_alt_text(batch, analysis)
    return ManifestRow(
        source_path=relative_path.replace("\\", "/"),
        new_filename=filename,
        folder="hero" if analysis["hero_candidate"] else "gallery",
        alt_text=alt_text,
    )


def analyze_image(image_path: Path) -> dict:
    with Image.open(image_path) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        width, height = image.size
        grayscale = image.convert("L")
        brightness = ImageStat.Stat(grayscale).mean[0]
        contrast = ImageStat.Stat(grayscale).stddev[0]
        edge_density = ImageStat.Stat(grayscale.filter(ImageFilter.FIND_EDGES)).mean[0]
        orientation = "horizontal" if width > height else "vertical" if height > width else "square"
        crop_feel = "wide crop" if width / max(height, 1) >= 1.45 else "tight crop" if height / max(width, 1) >= 1.3 else "medium crop"
        brightness_label = (
            "bright" if brightness >= 180 else "light" if brightness >= 140 else "balanced" if brightness >= 95 else "moody"
        )
        contrast_label = "crisp" if contrast >= 65 else "soft" if contrast < 40 else "balanced"
        composition_label = "clean negative space" if edge_density < 28 else "layered background" if edge_density > 52 else "balanced framing"
        hero_candidate = orientation == "horizontal" and width >= 1800 and contrast >= 35 and edge_density < 70
        return {
            "orientation": orientation,
            "crop_feel": crop_feel,
            "brightness_label": brightness_label,
            "contrast_label": contrast_label,
            "composition_label": composition_label,
            "light_direction": _guess_light_direction(grayscale),
            "hero_candidate": hero_candidate,
        }


def choose_filename(batch: BatchInput, keyword_pool: KeywordPool, analysis: dict, existing_names: set[str]) -> str:
    rotation = len(existing_names)
    service = keyword_pool.service_phrases[rotation % len(keyword_pool.service_phrases)]
    location = keyword_pool.plausible_locations[rotation % len(keyword_pool.plausible_locations)]
    modifier = keyword_pool.premium_modifiers[rotation % len(keyword_pool.premium_modifiers)]
    setting = batch.setting_tags[rotation % len(batch.setting_tags)] if batch.setting_tags else (
        "studio" if analysis["orientation"] == "vertical" else "outdoor"
    )
    patterns = [
        f"{location}-{service}.jpg",
        f"{service}-{location}.jpg",
        f"{modifier}-{service}-{location}.jpg" if analysis["hero_candidate"] else "",
        f"{service}-{setting}-{location}.jpg",
        f"{setting}-{service}-{location}.jpg",
        f"{location}-{modifier}-{service}.jpg" if analysis["hero_candidate"] else "",
    ]
    for candidate in patterns:
        clean = _sanitize_filename(candidate)
        if clean and clean not in existing_names:
            return clean
    for extra_location in keyword_pool.plausible_locations:
        clean = _sanitize_filename(f"{service}-{extra_location}.jpg")
        if clean and clean not in existing_names:
            return clean
    raise ValueError("Could not create a unique filename in rules-based mode.")


def build_alt_text(batch: BatchInput, analysis: dict) -> str:
    genre_label = batch.genre.strip().lower() or "portrait"
    service_label = batch.service_type.strip().lower() or "photography"
    city_label = batch.market_location.strip()
    setting_label = batch.setting_tags[0] if batch.setting_tags else ("studio" if analysis["orientation"] == "vertical" else "outdoor")
    parts = [
        f"{analysis['orientation'].capitalize()} {genre_label} image for {service_label}",
        f"with a {analysis['crop_feel']}",
        f"a {analysis['contrast_label']} finish",
        f"{analysis['brightness_label']} lighting",
        f"{analysis['composition_label']}",
        f"in a {setting_label} setting",
        f"with light appearing strongest from the {analysis['light_direction']}",
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


def _extract_site_terms(website_summary: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z][a-zA-Z-]{3,}", website_summary.lower())
    stop_words = {
        "with", "from", "that", "this", "your", "their", "have", "about", "home", "contact", "portfolio",
        "gallery", "services", "photography", "photographer", "studio", "image", "images", "page", "pages",
    }
    counts: dict[str, int] = {}
    for token in tokens:
        if token in stop_words:
            continue
        counts[token] = counts.get(token, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [word for word, _count in ranked[:4]]


def _brand_modifiers(brand_style: str) -> list[str]:
    style = brand_style.lower()
    if "luxury" in style:
        return ["luxury", "bespoke", "editorial", "signature"]
    if "editorial" in style:
        return ["editorial", "signature", "refined", "bespoke"]
    if "classic" in style:
        return ["classic", "timeless", "refined", "signature"]
    if "family" in style:
        return ["warm", "natural", "signature", "refined"]
    if "corporate" in style:
        return ["executive", "professional", "refined", "signature"]
    return ["refined", "signature", "editorial", "bespoke"]


def _guess_light_direction(grayscale: Image.Image) -> str:
    width, height = grayscale.size
    left_mean = ImageStat.Stat(grayscale.crop((0, 0, width // 2, height))).mean[0]
    right_mean = ImageStat.Stat(grayscale.crop((width // 2, 0, width, height))).mean[0]
    top_mean = ImageStat.Stat(grayscale.crop((0, 0, width, height // 2))).mean[0]
    bottom_mean = ImageStat.Stat(grayscale.crop((0, height // 2, width, height))).mean[0]
    horizontal_delta = abs(left_mean - right_mean)
    vertical_delta = abs(top_mean - bottom_mean)
    if horizontal_delta >= vertical_delta and horizontal_delta > 8:
        return "left" if left_mean > right_mean else "right"
    if vertical_delta > 8:
        return "top" if top_mean > bottom_mean else "bottom"
    return "front"


def _domain_label(url: str) -> str:
    host = urlparse(url).netloc.lower().replace("www.", "")
    label = host.split(".")[0] if host else ""
    return _slug_words(label, fallback="")


def _sanitize_filename(value: str) -> str:
    stem = Path(value).stem.lower()
    stem = "".join(ch if ch.isalpha() or ch == "-" else "-" for ch in stem)
    while "--" in stem:
        stem = stem.replace("--", "-")
    stem = stem.strip("-")
    return f"{stem}.jpg" if stem else ""


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
