from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps


def create_thumbnail(source_image: Path, thumb_path: Path, size: tuple[int, int] = (180, 120)) -> None:
    thumb_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source_image) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.thumbnail(size, Image.Resampling.LANCZOS)
        image.save(thumb_path, format="JPEG", quality=82)


def image_to_data_url(path: str | None) -> str:
    if not path:
        return ""
    payload = Path(path).read_bytes()
    encoded = base64.b64encode(payload).decode("utf-8")
    return f"data:image/jpeg;base64,{encoded}"


def image_to_html(data_url: str) -> str:
    if not data_url:
        return ""
    return f'<img src="{data_url}" width="140" style="border-radius:8px; object-fit:cover;" />'
