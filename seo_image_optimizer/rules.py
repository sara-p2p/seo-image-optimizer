from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image, ImageFilter, ImageOps, ImageStat

from .models import BatchInput, KeywordPool, ManifestRow


def build_keyword_pool(batch: BatchInput, website_summary: str = "") -> KeywordPool:
    genre_slug = _slug_words(batch.genre, fallback="portrait")
    service_slug = _canonical_service_slug(batch.service_type, batch.genre)
    city_slug = _slug_words(batch.market_location, fallback="local-market")
    website_terms = _extract_site_terms(website_summary)
    modifier_pool = _brand_modifiers(batch.brand_style)

    service_phrases = _dedupe(
        [
            f"{genre_slug}-{service_slug}",
            f"{service_slug}-{genre_slug}" if service_slug != genre_slug else "",
            _canonical_service_phrase(batch.service_type, batch.genre),
            f"{genre_slug}-photographer" if service_slug != "photographer" else "",
            "portrait-photographer" if genre_slug != "portrait" else "",
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
    rotation = len(existing_names)
    analysis = analyze_image(image_path)
    filename = choose_filename(batch, keyword_pool, analysis, existing_names)
    alt_text = build_alt_text(batch, analysis, rotation)
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
        brightness = ImageStat.Stat(grayscale).mean[0]
        contrast = ImageStat.Stat(grayscale).stddev[0]
        edge_density = ImageStat.Stat(grayscale.filter(ImageFilter.FIND_EDGES)).mean[0]
        channel_delta = max(
            abs(color_stat.mean[0] - color_stat.mean[1]),
            abs(color_stat.mean[1] - color_stat.mean[2]),
            abs(color_stat.mean[0] - color_stat.mean[2]),
        )
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
            "is_black_and_white": channel_delta < 6,
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


def build_alt_text(batch: BatchInput, analysis: dict, rotation: int) -> str:
    rotation_seed = len(batch.studio_name) + len(batch.market_location) + len(batch.genre) + rotation
    genre_label = _display_phrase(batch.genre, fallback="portrait")
    service_label = _display_phrase(_canonical_service_phrase(batch.service_type, batch.genre), fallback="photography")
    location_label = batch.market_location.strip()
    studio_label = batch.studio_name.strip()
    setting_label = batch.setting_tags[0] if batch.setting_tags else ("studio" if analysis["orientation"] == "vertical" else "outdoor")
    style_word = _pick_from_bank(_style_word_bank(batch.brand_style), rotation_seed + len(service_label))
    mood_word = _pick_from_bank(_mood_word_bank(batch.brand_style), rotation_seed + len(genre_label))
    location_phrase = _location_phrase_bank(location_label)
    monochrome_prefix = "Black and white " if analysis["is_black_and_white"] else ""
    templates = [
        f"{monochrome_prefix}{genre_label} portrait by {studio_label} {location_phrase}",
        f"{monochrome_prefix}{style_word} {genre_label} photography by {studio_label} {location_phrase}",
        f"{monochrome_prefix}{service_label} portrait created by {studio_label} {location_phrase}",
        f"{monochrome_prefix}{mood_word} {genre_label} image from {studio_label} {location_phrase}",
        f"{monochrome_prefix}{style_word} {service_label} session by {studio_label} {location_phrase}",
        f"{monochrome_prefix}{genre_label} portrait in a {setting_label} setting by {studio_label} {location_phrase}",
        f"{monochrome_prefix}{mood_word} {service_label} photography by {studio_label} in {location_label}",
        f"{monochrome_prefix}{style_word} {genre_label} portrait for {location_label} by {studio_label}",
    ]
    selected = templates[rotation_seed % len(templates)]
    selected = " ".join(selected.split()).strip()
    return selected[0].upper() + selected[1:] + "."


def _slug_words(value: str, fallback: str) -> str:
    words = []
    for raw in value.lower().replace("&", " ").replace("/", " ").split():
        clean = "".join(ch for ch in raw if ch.isalpha() or ch == "-")
        if clean:
            words.append(clean)
    return "-".join(words[:4]) or fallback


def _canonical_service_slug(service_type: str, genre: str) -> str:
    raw = f"{service_type} {genre}".lower()
    mapping = [
        ("headshot", "headshot-photographer"),
        ("branding", "branding-photographer"),
        ("business", "business-photographer"),
        ("boudoir", "boudoir-photographer"),
        ("newborn", "newborn-photographer"),
        ("maternity", "maternity-photographer"),
        ("family", "family-photographer"),
        ("portrait", "portrait-photographer"),
        ("senior", "senior-photographer"),
        ("wedding", "wedding-photographer"),
        ("engagement", "engagement-photographer"),
        ("corporate", "corporate-photographer"),
        ("branding session", "branding-photographer"),
    ]
    for needle, canonical in mapping:
        if needle in raw:
            return canonical
    if "photographer" in raw:
        words = [part for part in _slug_words(raw, fallback="portrait-photographer").split("-") if part != "photography"]
        return "-".join(words[:3]) or "portrait-photographer"
    base = _slug_words(service_type, fallback=_slug_words(genre, fallback="portrait"))
    if base.endswith("photography"):
        base = base[: -len("photography")].strip("-")
    if not base:
        base = "portrait"
    if base.endswith("photographer"):
        return base
    return f"{base}-photographer"


def _canonical_service_phrase(service_type: str, genre: str) -> str:
    return _canonical_service_slug(service_type, genre)


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


def _style_word_bank(brand_style: str) -> list[str]:
    banks = {
        "luxury": [
            "luxury", "bespoke", "elevated", "polished", "sophisticated", "refined", "curated", "graceful",
            "luminous", "tailored", "premium", "high-end", "signature", "artful", "styled", "glossy",
            "fashion-led", "editorial", "sleek", "poised", "elegant", "distinctive", "opulent", "modern",
            "softly-lit", "intentional", "cinematic", "upscale", "designer", "tasteful", "classic-luxury",
            "exclusive", "confident", "statement-making", "well-appointed", "clean-lined", "prestige",
            "fine-art", "dramatic", "chic", "glamorous", "beautifully-styled", "metropolitan", "deluxe",
            "wealth-inspired", "richly-detailed", "gracious", "timeless", "atelier-inspired", "magazine-worthy",
        ],
        "editorial": [
            "editorial", "fashion-inspired", "styled", "modern", "directional", "polished", "cinematic",
            "bold", "sleek", "graphic", "intentional", "story-driven", "magazine-style", "cool-toned",
            "sharp", "clean", "contemporary", "high-contrast", "textured", "artful", "elevated", "striking",
            "curated", "minimal", "refined", "vogue-inspired", "campaign-ready", "stylized", "confident",
            "designer-led", "trend-forward", "tailored", "framed", "structured", "dramatic", "composed",
            "glossy", "studio-led", "photographic", "aesthetic", "gallery-style", "fashion-forward",
            "modern-classic", "image-led", "creative", "crisp", "clean-lined", "visual", "distinctive", "posed",
        ],
        "classic": [
            "classic", "timeless", "elegant", "refined", "polished", "graceful", "soft", "clean", "traditional",
            "understated", "balanced", "simple", "beautiful", "enduring", "tailored", "tasteful", "composed",
            "natural", "light-filled", "warm", "heirloom", "well-framed", "gentle", "calm", "lovely",
            "finished", "sophisticated", "neutral", "gracious", "formal", "bright", "subtle", "quiet",
            "classic-portrait", "true-to-life", "restful", "harmonious", "softly-styled", "familiar",
            "cleanly-lit", "steady", "pleasing", "structured", "poised", "eased", "tidy", "clear", "settled",
            "measured", "heritage-inspired",
        ],
        "family": [
            "warm", "natural", "relaxed", "heartfelt", "joyful", "soft", "playful", "loving", "easygoing",
            "bright", "sunny", "gentle", "candid", "connected", "cozy", "welcoming", "sweet", "light-filled",
            "friendly", "honest", "easy", "tender", "lively", "carefree", "comfortable", "everyday-beautiful",
            "close-knit", "cheerful", "homey", "organic", "simple", "calm", "smiling", "emotion-led", "fun",
            "open-air", "sun-washed", "family-centered", "real", "sincere", "softly-lit", "playful-hearted",
            "gentle-toned", "memory-filled", "lovely", "inviting", "grounded", "fresh", "casual", "sunlit",
        ],
        "corporate": [
            "professional", "executive", "polished", "modern", "refined", "corporate", "clean", "sharp",
            "confident", "strategic", "credible", "business-ready", "sleek", "tailored", "structured",
            "leader-focused", "brand-forward", "elevated", "current", "studio-ready", "well-lit", "clear",
            "profile-ready", "presentable", "high-trust", "reliable", "streamlined", "focused", "smart",
            "composed", "capable", "well-framed", "boardroom-ready", "strong", "measured", "distinctive",
            "contemporary", "business-minded", "market-facing", "authoritative", "sharp-lined", "modern-classic",
            "clean-cut", "up-to-date", "professional-grade", "brand-consistent", "client-facing", "solid",
            "intentional", "presentation-ready",
        ],
        "refined": [
            "refined", "polished", "elegant", "clean", "modern", "soft", "intentional", "graceful", "tailored",
            "timeless", "balanced", "warm", "light-filled", "composed", "sophisticated", "simple", "elevated",
            "subtle", "tasteful", "studio-led", "calm", "bright", "curated", "sleek", "beautiful", "classic",
            "softly-lit", "clear", "well-framed", "artful", "gentle", "natural", "careful", "considered",
            "restrained", "editorial-leaning", "signature", "quiet-luxury", "thoughtful", "lush", "glowing",
            "poised", "distinctive", "finished", "neutral", "gracious", "fine-art", "light-toned", "serene",
            "high-touch",
        ],
    }
    return banks.get(brand_style.lower(), banks["refined"])


def _mood_word_bank(brand_style: str) -> list[str]:
    banks = {
        "luxury": [
            "elevated", "glamorous", "refined", "polished", "dramatic", "bespoke", "signature", "couture",
            "graceful", "confident", "striking", "luminous", "artful", "fashion-forward", "opulent", "sleek",
            "tailored", "intentional", "glossy", "exclusive", "high-style", "gallery-worthy", "poised",
            "sophisticated", "cinematic", "radiant", "rich", "designer", "premium", "well-styled", "soft-glow",
            "chic", "high-end", "tasteful", "dramatically-lit", "magnificent", "salon-quality", "metro", "plush",
            "runway-inspired", "statuesque", "vibrant", "showpiece", "beautifully-finished", "collector-worthy",
            "silken", "grand", "glowing", "decadent", "editorial",
        ],
        "editorial": [
            "stylized", "fashion-led", "bold", "graphic", "structured", "modern", "curated", "composed",
            "directional", "magazine-style", "cool", "sleek", "sharp", "visual", "camera-ready", "campaign-ready",
            "intentional", "story-driven", "framed", "angular", "striking", "minimal", "clean", "cinematic",
            "art-directed", "statement", "cool-toned", "dramatic", "aesthetic", "high-style", "edgy", "measured",
            "sophisticated", "glossy", "high-contrast", "designed", "distinctive", "modern-classic", "textured",
            "controlled", "posed", "studio-shaped", "publication-ready", "fashionable", "confident", "elevated",
            "creative", "deliberate", "artful", "visual-first",
        ],
        "classic": [
            "timeless", "elegant", "graceful", "soft", "balanced", "calm", "light", "traditional", "polished",
            "formal", "gentle", "beautiful", "clean", "refined", "understated", "warm", "measured", "quiet",
            "softly-lit", "familiar", "harmonious", "composed", "settled", "natural", "simple", "lovely", "clear",
            "steady", "restful", "heirloom", "heritage-inspired", "poised", "bright", "tasteful", "enduring",
            "true-to-life", "neutral", "gracious", "tidy", "structured", "pleasant", "finished", "delicate",
            "subtle", "clean-lined", "well-framed", "soft-toned", "calming", "steady-lit", "classic",
        ],
        "family": [
            "warm", "joyful", "relaxed", "heartfelt", "playful", "connected", "candid", "gentle", "sunny",
            "loving", "easygoing", "natural", "cozy", "friendly", "sweet", "soft", "light-filled", "open",
            "carefree", "happy", "comfortable", "sincere", "fresh", "lively", "real", "welcoming", "organic",
            "homey", "bright", "lovely", "emotion-filled", "easy", "supportive", "family-centered", "cheerful",
            "lovely-lit", "tender", "joy-led", "sun-washed", "smiling", "memory-rich", "intimate", "grounded",
            "casual", "alive", "kind", "true", "honest", "sweet-natured", "sunlit",
        ],
        "corporate": [
            "professional", "confident", "polished", "strategic", "credible", "executive", "modern", "sharp",
            "clean", "focused", "clear", "presentable", "business-ready", "leader-focused", "authoritative",
            "refined", "structured", "brand-forward", "strong", "smart", "capable", "current", "tailored",
            "reliable", "streamlined", "purposeful", "composed", "distinctive", "corporate", "market-facing",
            "solid", "high-trust", "well-lit", "precise", "boardroom-ready", "professional-grade", "clean-cut",
            "effective", "prepared", "measured", "competent", "sharp-lined", "confidently-lit", "clear-framed",
            "positioned", "ready", "structured-light", "brand-consistent", "decisive", "well-styled",
        ],
        "refined": [
            "refined", "polished", "graceful", "elegant", "soft", "intentional", "balanced", "timeless", "calm",
            "light-filled", "composed", "tasteful", "subtle", "clean", "warm", "curated", "poised", "finished",
            "beautiful", "serene", "sleek", "gentle", "studio-led", "neutral", "clear", "measured", "artful",
            "softly-lit", "well-framed", "elevated", "high-touch", "considered", "quiet-luxury", "lovely", "lush",
            "glowing", "signature", "restrained", "thoughtful", "bright", "light-toned", "classic", "distinctive",
            "careful", "tailored", "settled", "fine-art", "modern", "gracious", "harmonious",
        ],
    }
    return banks.get(brand_style.lower(), banks["refined"])


def _pick_from_bank(words: list[str], seed: int) -> str:
    return words[seed % len(words)]


def _location_phrase_bank(location: str) -> str:
    clean = location.strip()
    return [
        f"in {clean}",
        f"serving {clean}",
        f"based in {clean}",
        f"for {clean} clients",
        f"created for {clean}",
    ][len(clean) % 5] if clean else "for local clients"


def _display_phrase(value: str, fallback: str) -> str:
    words = [part for part in re.split(r"[-\s]+", value.strip()) if part]
    return " ".join(words).lower() if words else fallback


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
