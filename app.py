from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory

import streamlit as st
from dotenv import load_dotenv

from seo_image_optimizer.models import BatchInput
from seo_image_optimizer.pipeline import process_batch


load_dotenv()

st.set_page_config(page_title="SEO Image Optimizer", layout="wide")
st.title("SEO Image Optimizer")
st.caption("Upload a finished image zip, enter the studio details, and generate downloadable SEO-ready hero and gallery exports.")

with st.sidebar:
    st.header("Processing")
    processing_mode = st.radio(
        "Mode",
        options=["Auto", "Rules-only"],
        help="Auto uses the OpenAI API when an API key is present and falls back to local rules when it is not.",
    )
    st.header("OpenAI")
    api_key = st.text_input(
        "API key",
        value=os.getenv("OPENAI_API_KEY", ""),
        type="password",
        help="Stored only for this session unless you put it in .env.",
    )
    model = st.text_input("Model", value=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))

with st.form("optimizer_form"):
    uploaded_zip = st.file_uploader("Image ZIP", type=["zip"])
    studio_name = st.text_input("Photographer or studio name")
    website_url = st.text_input("Website URL", placeholder="https://example.com")
    genre = st.text_input("Genre", placeholder="Headshots, family, boudoir, newborn, branding...")
    business_address = st.text_input("Business address")
    market_location = st.text_input("Primary market location", placeholder="Dallas, TX")
    notes = st.text_area("Extra business notes or service emphasis", height=110)
    submitted = st.form_submit_button("Process Batch", type="primary")


def _read_thumbnail_bytes(path: str | None) -> bytes | None:
    if not path:
        return None
    file_path = Path(path)
    if not file_path.exists():
        return None
    return file_path.read_bytes()


def _store_result_for_reruns(result) -> None:
    st.session_state["last_result"] = {
        "processing_summary": result.processing_summary,
        "processed_count": len(result.rows),
        "hero_count": sum(1 for row in result.rows if row.folder == "hero"),
        "gallery_count": sum(1 for row in result.rows if row.folder == "gallery"),
        "skipped_files": result.skipped_files,
        "zip_bytes": result.processed_zip_path.read_bytes(),
        "csv_bytes": result.csv_path.read_bytes(),
        "rows": [
            {
                "new_filename": row.new_filename,
                "alt_text": row.alt_text,
                "thumbnail_bytes": _read_thumbnail_bytes(row.thumbnail_path),
            }
            for row in result.rows
        ],
    }


def render_results_table(rows) -> None:
    header_a, header_b, header_c = st.columns([1.2, 1.5, 3.3])
    header_a.markdown("**Thumbnail**")
    header_b.markdown("**New Filename**")
    header_c.markdown("**Alt Text**")
    st.divider()

    for row in rows:
        col_a, col_b, col_c = st.columns([1.2, 1.5, 3.3])
        with col_a:
            if row.get("thumbnail_bytes"):
                st.image(row["thumbnail_bytes"], width=140)
            else:
                st.caption("No preview")
        with col_b:
            st.code(row["new_filename"], language=None)
        with col_c:
            st.write(row["alt_text"])
        st.divider()


def render_persisted_result() -> None:
    result = st.session_state.get("last_result")
    if not result:
        return

    st.info(f"Processed with {result['processing_summary']}.")

    metric_a, metric_b, metric_c = st.columns(3)
    metric_a.metric("Processed Images", result["processed_count"])
    metric_b.metric("Hero Images", result["hero_count"])
    metric_c.metric("Gallery Images", result["gallery_count"])

    if result["skipped_files"]:
        st.warning("Some files were skipped during export: " + ", ".join(result["skipped_files"]))

    download_a, download_b = st.columns(2)
    download_a.download_button(
        "Download Processed ZIP",
        data=result["zip_bytes"],
        file_name="processed_images.zip",
        mime="application/zip",
    )
    download_b.download_button(
        "Download Alt Text CSV",
        data=result["csv_bytes"],
        file_name="alt_text.csv",
        mime="text/csv",
    )

    st.subheader("Filename and Alt Text Review")
    render_results_table(result["rows"])


if submitted:
    missing = [
        label
        for label, value in (
            ("Image ZIP", uploaded_zip),
            ("Studio name", studio_name),
            ("Website URL", website_url),
            ("Genre", genre),
            ("Business address", business_address),
            ("Primary market location", market_location),
        )
        if not value
    ]
    if missing:
        st.error(f"Missing required inputs: {', '.join(missing)}")
    else:
        batch = BatchInput(
            studio_name=studio_name.strip(),
            website_url=website_url.strip(),
            genre=genre.strip(),
            market_location=market_location.strip(),
            business_address=business_address.strip(),
            notes=notes.strip(),
            openai_api_key=api_key.strip(),
            openai_model=model.strip() or "gpt-4.1-mini",
            processing_mode="rules" if processing_mode == "Rules-only" else "auto",
        )

        with TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            input_zip_path = tmp_root / "input.zip"
            input_zip_path.write_bytes(uploaded_zip.getvalue())

            with st.spinner("Researching the website, analyzing images, and building the delivery package..."):
                try:
                    result = process_batch(batch, input_zip_path, tmp_root / "job")
                except Exception as exc:
                    st.exception(exc)
                else:
                    _store_result_for_reruns(result)

render_persisted_result()
