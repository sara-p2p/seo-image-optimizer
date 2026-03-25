from __future__ import annotations

from pathlib import Path

from .delivery import (
    extract_images,
    export_images,
    package_delivery,
    write_alt_text_csv,
    write_failed_csv,
    write_manifest_csv,
)
from .models import BatchInput, ProcessResult
from . import ai, rules
from .thumbnails import create_thumbnail
from .website_research import fetch_site_summary


def process_batch(batch: BatchInput, input_zip: Path, working_root: Path) -> ProcessResult:
    working_root.mkdir(parents=True, exist_ok=True)
    website_summary = fetch_site_summary(batch.website_url)
    engine_name, keyword_pool_builder, manifest_row_builder = _choose_engine(batch)
    keyword_pool = keyword_pool_builder(batch, website_summary)

    extracted_dir = working_root / "extracted"
    output_dir = working_root / "delivery"
    thumbs_dir = working_root / "thumbs"
    exported = extract_images(input_zip, extracted_dir)
    if not exported:
        raise ValueError("No supported images were found in the uploaded ZIP.")
    rows = []
    existing_names: set[str] = set()

    for image_path, relative_path in exported:
        row = manifest_row_builder(batch, keyword_pool, image_path, relative_path, existing_names)
        existing_names.add(row.new_filename)
        thumb_path = thumbs_dir / f"{Path(row.new_filename).stem}.jpg"
        create_thumbnail(image_path, thumb_path)
        row.thumbnail_path = str(thumb_path)
        rows.append(row)

    _cap_hero_assignments(rows)
    skipped_files = export_images(rows, extracted_dir, output_dir)
    manifest_path = working_root / "manifest.csv"
    csv_path = output_dir / "alt_text.csv"
    zip_path = working_root / "processed_images.zip"
    failed_path = output_dir / "failed_images.csv" if skipped_files else None

    write_manifest_csv(rows, manifest_path)
    write_alt_text_csv(rows, csv_path)
    if skipped_files and failed_path:
        write_failed_csv(skipped_files, failed_path)
    package_delivery(output_dir, zip_path)

    return ProcessResult(
        processed_zip_path=zip_path,
        csv_path=csv_path,
        manifest_path=manifest_path,
        failed_path=failed_path,
        rows=rows,
        skipped_files=skipped_files,
        processing_summary=engine_name,
    )


def _cap_hero_assignments(rows) -> None:
    if not rows:
        return
    hero_limit = 1 if len(rows) <= 8 else 2 if len(rows) <= 20 else 4 if len(rows) <= 60 else 6
    hero_count = 0
    for row in rows:
        if row.folder != "hero":
            continue
        hero_count += 1
        if hero_count > hero_limit:
            row.folder = "gallery"


def _choose_engine(batch: BatchInput):
    wants_rules_only = batch.processing_mode == "rules"
    has_api = bool(batch.openai_api_key.strip())
    if not wants_rules_only and has_api:
        return "AI-assisted mode", ai.build_keyword_pool, ai.generate_manifest_row
    return "Rules-only mode", rules.build_keyword_pool, rules.generate_manifest_row
