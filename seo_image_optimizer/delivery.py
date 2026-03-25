from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

from PIL import Image, ImageOps

from .models import ManifestRow


SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}


def extract_images(input_zip: Path, extraction_dir: Path) -> list[tuple[Path, str]]:
    extraction_dir.mkdir(parents=True, exist_ok=True)
    extracted: list[tuple[Path, str]] = []
    with zipfile.ZipFile(input_zip) as archive:
        for member in archive.infolist():
            name = member.filename
            if member.is_dir():
                continue
            path = Path(name)
            if _is_hidden_or_ignored(path):
                continue
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            archive.extract(member, extraction_dir)
            extracted_path = extraction_dir / path
            extracted.append((extracted_path, path.as_posix()))
    return extracted


def export_images(rows: list[ManifestRow], extracted_dir: Path, output_dir: Path) -> list[str]:
    skipped: list[str] = []
    output_dir.mkdir(parents=True, exist_ok=True)
    for row in rows:
        source = extracted_dir / row.source_path
        destination = output_dir / row.folder / row.new_filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with Image.open(source) as image:
                image = ImageOps.exif_transpose(image).convert("RGB")
                target_edge = 2560 if row.folder == "hero" else 1600
                soft_limit = 500_000 if row.folder == "hero" else 200_000
                optimized = resize_to_long_edge(image, target_edge)
                save_jpeg_under_limit(optimized, destination, soft_limit)
                row.output_path = str(destination)
        except Exception:
            skipped.append(row.source_path)
    return skipped


def resize_to_long_edge(image: Image.Image, max_long_edge: int) -> Image.Image:
    width, height = image.size
    longest = max(width, height)
    if longest <= max_long_edge:
        return image.copy()
    scale = max_long_edge / float(longest)
    new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return image.resize(new_size, Image.Resampling.LANCZOS)


def save_jpeg_under_limit(image: Image.Image, destination: Path, soft_limit: int) -> None:
    quality_steps = [88, 84, 80, 76, 72, 68]
    best_bytes: bytes | None = None
    for quality in quality_steps:
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=quality, optimize=True, progressive=True)
        payload = buffer.getvalue()
        if best_bytes is None:
            best_bytes = payload
        if len(payload) <= soft_limit:
            best_bytes = payload
            break
    destination.write_bytes(best_bytes or b"")


def write_manifest_csv(rows: list[ManifestRow], destination: Path) -> None:
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["source_path", "new_filename", "folder", "alt_text"])
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "source_path": row.source_path,
                    "new_filename": row.new_filename,
                    "folder": row.folder,
                    "alt_text": row.alt_text,
                }
            )


def write_alt_text_csv(rows: list[ManifestRow], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["new_filename", "alt_text"])
        writer.writeheader()
        for row in rows:
            writer.writerow({"new_filename": row.new_filename, "alt_text": row.alt_text})


def write_failed_csv(skipped_files: list[str], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["source_path"])
        writer.writeheader()
        for path in skipped_files:
            writer.writerow({"source_path": path})


def package_delivery(output_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=4) as archive:
        for file_path in output_dir.rglob("*"):
            if file_path.is_file():
                archive.write(file_path, file_path.relative_to(output_dir))


def _is_hidden_or_ignored(path: Path) -> bool:
    parts = {part.lower() for part in path.parts}
    if any(part.startswith(".") for part in path.parts):
        return True
    ignored = {"__macosx", ".ds_store", "thumbs.db"}
    return bool(parts & ignored)
