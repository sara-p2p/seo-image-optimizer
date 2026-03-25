from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image, ImageFilter, ImageOps, ImageStat

from .models import BatchInput, KeywordPool, ManifestRow


GENRE_CONFIG = {
    "Boudoir": {
        "service_keywords": ["boudoir-photography", "boudoir-photographer", "editorial-boudoir-photography"],
        "noun_phrases": ["boudoir portrait", "boudoir photo", "boudoir photograph", "boudoir image"],
        "safe_adjectives": [
            "elegant", "refined", "editorial", "luxury", "sophisticated", "polished", "tasteful", "timeless",
            "elevated", "graceful", "beautiful", "soft", "modern", "classic", "signature",
        ],
    },
    "Branding": {
        "service_keywords": ["branding-photography", "branding-photographer", "personal-branding-photography"],
        "noun_phrases": ["branding portrait", "branding photo", "branding photograph", "branding image"],
        "safe_adjectives": [
            "professional", "modern", "polished", "refined", "elevated", "editorial", "clean", "strategic",
            "confident", "sleek", "contemporary", "intentional", "strong", "signature", "distinctive",
        ],
    },
    "Corporate": {
        "service_keywords": ["corporate-photography", "corporate-photographer", "executive-headshot-photography"],
        "noun_phrases": ["corporate portrait", "executive photo", "corporate photograph", "professional image"],
        "safe_adjectives": [
            "professional", "executive", "polished", "refined", "modern", "credible", "confident", "clean",
            "sharp", "strategic", "tailored", "elevated", "presentable", "distinctive", "clear",
        ],
    },
    "Family": {
        "service_keywords": ["family-photography", "family-photographer", "outdoor-family-photography"],
        "noun_phrases": ["family portrait", "family photo", "family photograph", "family image"],
        "safe_adjectives": [
            "warm", "natural", "joyful", "relaxed", "timeless", "classic", "heartfelt", "light-filled",
            "soft", "beautiful", "playful", "cheerful", "gentle", "sunlit", "welcoming",
        ],
    },
    "Headshots": {
        "service_keywords": ["headshot-photography", "headshot-photographer", "professional-headshots"],
        "noun_phrases": ["headshot portrait", "headshot photo", "headshot photograph", "professional image"],
        "safe_adjectives": [
            "professional", "clean", "polished", "modern", "refined", "executive", "clear", "confident",
            "tailored", "elevated", "sharp", "distinctive", "current", "sleek", "credible",
        ],
    },
    "Maternity": {
        "service_keywords": ["maternity-photography", "maternity-photographer", "studio-maternity-photography"],
        "noun_phrases": ["maternity portrait", "maternity photo", "maternity photograph", "maternity image"],
        "safe_adjectives": [
            "elegant", "soft", "timeless", "refined", "beautiful", "warm", "graceful", "light-filled",
            "classic", "editorial", "polished", "gentle", "elevated", "serene", "signature",
        ],
    },
    "Newborn": {
        "service_keywords": ["newborn-photography", "newborn-photographer", "studio-newborn-photography"],
        "noun_phrases": ["newborn portrait", "newborn photo", "newborn photograph", "newborn image"],
        "safe_adjectives": [
            "soft", "gentle", "timeless", "beautiful", "classic", "light-filled", "warm", "refined",
            "peaceful", "elegant", "serene", "delicate", "natural", "sweet", "polished",
        ],
    },
    "Portrait": {
        "service_keywords": ["portrait-photography", "portrait-photographer", "editorial-portrait-photography"],
        "noun_phrases": ["portrait", "portrait photo", "portrait photograph", "portrait image"],
        "safe_adjectives": [
            "refined", "classic", "modern", "editorial", "elegant", "polished", "timeless", "beautiful",
            "light-filled", "signature", "elevated", "soft", "graceful", "distinctive", "clean",
        ],
    },
    "Senior": {
        "service_keywords": ["senior-photography", "senior-photographer", "senior-portrait-photography"],
        "noun_phrases": ["senior portrait", "senior photo", "senior photograph", "senior image"],
        "safe_adjectives": [
            "modern", "timeless", "refined", "light-filled", "beautiful", "polished", "classic", "elevated",
            "natural", "confident", "clean", "signature", "bright", "distinctive", "graceful",
        ],
    },
    "Wedding": {
        "service_keywords": ["wedding-photography", "wedding-photographer", "editorial-wedding-photography"],
        "noun_phrases": ["wedding portrait", "wedding photo", "wedding photograph", "wedding image"],
        "safe_adjectives": [
            "elegant", "timeless", "editorial", "romantic", "luxury", "refined", "polished", "beautiful",
            "light-filled", "classic", "graceful", "elevated", "signature", "soft", "sophisticated",
        ],
    },
}

STYLE_BANKS = {
    "Luxury": [
        "luxury", "bespoke", "refined", "elevated", "polished", "sophisticated", "elegant", "premium", "high-end", "signature",
        "graceful", "timeless", "curated", "tailored", "upscale", "artful", "sleek", "luminous", "exclusive", "tasteful",
    ],
    "Editorial": [
        "editorial", "stylized", "modern", "polished", "cinematic", "fashion-inspired", "clean", "contemporary", "refined", "elevated",
        "distinctive", "sleek", "directional", "curated", "intentional", "magazine-style", "sharp", "composed", "visual", "tasteful",
    ],
    "Classic": [
        "classic", "timeless", "elegant", "refined", "graceful", "polished", "beautiful", "clean", "traditional", "soft",
        "light-filled", "balanced", "tasteful", "calm", "composed", "gentle", "warm", "understated", "enduring", "poised",
    ],
    "Family": [
        "warm", "natural", "joyful", "heartfelt", "relaxed", "playful", "light-filled", "soft", "welcoming", "gentle",
        "beautiful", "cheerful", "sunlit", "friendly", "timeless", "easygoing", "connected", "cozy", "bright", "lovely",
    ],
    "Corporate": [
        "professional", "executive", "polished", "modern", "clean", "confident", "credible", "refined", "sharp", "strategic",
        "tailored", "elevated", "clear", "presentable", "distinctive", "sleek", "contemporary", "focused", "strong", "smart",
    ],
    "Refined": [
        "refined", "polished", "elegant", "clean", "modern", "soft", "timeless", "graceful", "tasteful", "balanced",
        "beautiful", "composed", "light-filled", "subtle", "elevated", "signature", "clear", "gentle", "artful", "serene",
    ],
}

BANNED_WORDS = {
    "graphic", "edgy", "provocative", "suggestive", "explicit", "sensual", "seductive", "fetish", "risque",
}


def build_keyword_pool(batch: BatchInput, website_summary: str = "") -> KeywordPool:
    config = _genre_config(batch.genre)
    brand_words = _brand_words(batch.brand_styles)
    locations = _dedupe(
        _location_terms(batch.market_location)
        + [_slug_words(item, fallback="") for item in batch.additional_locations]
        + [_domain_label(batch.website_url)]
        + _extract_site_terms(website_summary)
    )
    return KeywordPool(
        service_phrases=config["service_keywords"],
        premium_modifiers=brand_words,
        plausible_locations=[item for item in locations if item][:8] or ["local-market"],
        alt_text_style_notes=config["safe_adjectives"],
        brand_summary=" ".join(
            part for part in [batch.studio_name, batch.genre, ", ".join(batch.brand_styles), batch.market_location] if part
        ),
    )


def generate_manifest_row(
    batch: BatchInput,
    keyword_pool: KeywordPool,
    image_path: Path,
    relative_path: str,
    existing_names: set[str],
) -> ManifestRow:
    rotation = len(existing_names)
    analysis = analyze_image(image_path)
    filename = choose_filename(batch, keyword_pool, analysis, existing_names, rotation)
    alt_text = build_alt_text(batch, keyword_pool, analysis, rotation)
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
        color_stat = ImageStat.Stat(image)
        contrast = ImageStat.Stat(grayscale).stddev[0]
        edge_density = ImageStat.Stat(grayscale.filter(ImageFilter.FIND_EDGES)).mean[0]
        channel_delta = max(
            abs(color_stat.mean[0] - color_stat.mean[1]),
            abs(color_stat.mean[1] - color_stat.mean[2]),
            abs(color_stat.mean[0] - color_stat.mean[2]),
        )
        orientation = "horizontal" if width > height else "vertical" if height > width else "square"
        hero_candidate = orientation == "horizontal" and width >= 1800 and contrast >= 35 and edge_density < 70
        return {
            "orientation": orientation,
            "is_black_and_white": channel_delta < 6,
            "hero_candidate": hero_candidate,
        }


def choose_filename(
    batch: BatchInput,
    keyword_pool: KeywordPool,
    analysis: dict,
    existing_names: set[str],
    rotation: int,
) -> str:
    service_phrase = keyword_pool.service_phrases[rotation % len(keyword_pool.service_phrases)]
    style_word = keyword_pool.premium_modifiers[rotation % len(keyword_pool.premium_modifiers)]
    primary_location = keyword_pool.plausible_locations[rotation % len(keyword_pool.plausible_locations)]
    secondary_location = keyword_pool.plausible_locations[(rotation + 1) % len(keyword_pool.plausible_locations)]
    patterns = [
        f"{primary_location}-{style_word}-{service_phrase}",
        f"{style_word}-{service_phrase}-{primary_location}",
        f"{primary_location}-{service_phrase}",
        f"{service_phrase}-{primary_location}",
        f"{primary_location}-{secondary_location}-{service_phrase}",
        f"{secondary_location}-{service_phrase}-{primary_location}",
    ]
    for candidate in patterns:
        clean = _sanitize_filename(candidate)
        if clean and clean not in existing_names:
            return clean
    for extra in keyword_pool.plausible_locations:
        clean = _sanitize_filename(f"{extra}-{service_phrase}")
        if clean and clean not in existing_names:
            return clean
    raise ValueError("Could not create a unique filename in rules-based mode.")


def build_alt_text(batch: BatchInput, keyword_pool: KeywordPool, analysis: dict, rotation: int) -> str:
    config = _genre_config(batch.genre)
    style_word = _safe_word(keyword_pool.premium_modifiers[rotation % len(keyword_pool.premium_modifiers)])
    adjective = _safe_word(config["safe_adjectives"][rotation % len(config["safe_adjectives"])])
    noun_phrase = config["noun_phrases"][rotation % len(config["noun_phrases"])]
    studio_label = batch.studio_name.strip()
    primary_location = _display_location(batch.market_location)
    nearby_phrase = _nearby_locations_phrase(batch.additional_locations)
    service_phrase = _display_phrase(keyword_pool.service_phrases[rotation % len(keyword_pool.service_phrases)])
    monochrome_prefix = "Black and white " if analysis["is_black_and_white"] else ""
    templates = [
        f"{monochrome_prefix}{adjective} {noun_phrase} by {studio_label}, proudly serving {primary_location}",
        f"{monochrome_prefix}{style_word} {noun_phrase} by {studio_label}, proudly serving {primary_location}",
        f"{monochrome_prefix}{adjective} {service_phrase} by {studio_label}, proudly serving {primary_location}",
        f"{monochrome_prefix}{noun_phrase} by {studio_label}, proudly serving {primary_location}{nearby_phrase}",
        f"{monochrome_prefix}{style_word} {service_phrase} from {studio_label}, proudly serving {primary_location}",
        f"{monochrome_prefix}{adjective} {noun_phrase} from {studio_label}, proudly serving {primary_location}{nearby_phrase}",
    ]
    selected = " ".join(templates[rotation % len(templates)].split()).strip()
    return selected[0].upper() + selected[1:] + "."


def _genre_config(genre: str) -> dict:
    return GENRE_CONFIG.get(genre, GENRE_CONFIG["Portrait"])


def _brand_words(brand_styles: list[str]) -> list[str]:
    combined: list[str] = []
    for style in brand_styles or ["Refined"]:
        combined.extend(STYLE_BANKS.get(style, STYLE_BANKS["Refined"]))
    filtered = [_safe_word(word) for word in combined]
    return _dedupe([word for word in filtered if word])


def _safe_word(word: str) -> str:
    cleaned = word.strip().lower()
    return "" if cleaned in BANNED_WORDS else cleaned


def _extract_site_terms(website_summary: str) -> list[str]:
    tokens = re.findall(r"[a-zA-Z][a-zA-Z-]{4,}", website_summary.lower())
    stop_words = {
        "about", "contact", "experience", "gallery", "portfolio", "services", "photography", "photographer",
        "studio", "images", "image", "home", "page",
    }
    ranked: dict[str, int] = {}
    for token in tokens:
        if token in stop_words:
            continue
        ranked[token] = ranked.get(token, 0) + 1
    results = []
    for word, _count in sorted(ranked.items(), key=lambda item: (-item[1], item[0])):
        slug = _slug_words(word, fallback="")
        if slug and slug not in results:
            results.append(slug)
        if len(results) == 3:
            break
    return results


def _location_terms(location: str) -> list[str]:
    clean = location.strip()
    if not clean:
        return ["local-market"]
    parts = [part.strip() for part in clean.split(",") if part.strip()]
    city = _slug_words(parts[0], fallback="local-market") if parts else "local-market"
    state = _state_slug(parts[1]) if len(parts) > 1 else ""
    terms = [city]
    if state:
        terms.append(f"{city}-{state}")
        terms.append(f"{city}-{_state_full_name(parts[1])}")
    return [item for item in terms if item]


def _display_location(location: str) -> str:
    return location.strip() or "your area"


def _nearby_locations_phrase(locations: list[str]) -> str:
    cleaned = [item.strip() for item in locations if item.strip()]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return f" and {cleaned[0]}"
    return f" and nearby areas like {', '.join(cleaned[:2])}"


def _display_phrase(value: str) -> str:
    words = [part for part in re.split(r"[-\s]+", value.strip()) if part]
    return " ".join(words).lower()


def _slug_words(value: str, fallback: str) -> str:
    words = []
    for raw in value.lower().replace("&", " ").replace("/", " ").split():
        clean = "".join(ch for ch in raw if ch.isalpha() or ch == "-")
        if clean:
            words.append(clean)
    return "-".join(words[:5]) or fallback


def _state_slug(value: str) -> str:
    cleaned = "".join(ch for ch in value.lower() if ch.isalpha())
    return cleaned[:2] if len(cleaned) >= 2 else cleaned


def _state_full_name(value: str) -> str:
    cleaned = _slug_words(value, fallback="")
    return cleaned or _state_slug(value)


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
