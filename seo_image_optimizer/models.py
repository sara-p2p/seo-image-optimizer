from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


FolderName = Literal["hero", "gallery"]


@dataclass(slots=True)
class BatchInput:
    studio_name: str
    website_url: str
    genre: str
    market_location: str
    brand_styles: list[str] = field(default_factory=list)
    setting_tags: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass(slots=True)
class KeywordPool:
    service_phrases: list[str]
    premium_modifiers: list[str]
    plausible_locations: list[str]
    alt_text_style_notes: list[str]
    brand_summary: str


@dataclass(slots=True)
class ManifestRow:
    source_path: str
    new_filename: str
    folder: FolderName
    alt_text: str
    thumbnail_path: str | None = None
    output_path: str | None = None


@dataclass(slots=True)
class ProcessResult:
    processed_zip_path: Path
    csv_path: Path
    manifest_path: Path
    failed_path: Path | None
    rows: list[ManifestRow]
    skipped_files: list[str] = field(default_factory=list)
    processing_summary: str = ""
