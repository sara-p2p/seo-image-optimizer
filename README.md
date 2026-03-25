# SEO Image Optimizer

SEO Image Optimizer is a Streamlit app for turning finished photography exports into web-ready deliverables for SEO and AI discovery.

Users can:

- upload a `.zip` of edited images
- enter the photographer or studio details
- generate a downloadable package with `hero/` and `gallery/`
- download `alt_text.csv`
- review thumbnails, filenames, and alt text in the browser

## Features

- researches the photographer website once per run
- uses a local rules-based workflow only
- strengthens results with structured inputs such as service keyword, market, brand style, and setting tags
- generates:
  - search-intent filenames
  - descriptive alt text
  - hero and gallery assignments
- exports compressed JPG derivatives
- packages outputs into `processed_images.zip`
- keeps results visible after download during the session

## Project layout

- `app.py` - Streamlit UI
- `seo_image_optimizer/pipeline.py` - orchestration
- `seo_image_optimizer/rules.py` - no-API fallback logic
- `seo_image_optimizer/delivery.py` - extraction, export, CSV generation, and ZIP packaging
- `seo_image_optimizer/website_research.py` - lightweight website scraping

## Local setup

1. Install Python 3.11 or newer.
2. Run the easiest option:

```powershell
install_and_run.bat
```

3. Or run manually:

```powershell
py -3 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Streamlit Community Cloud deployment

1. Push this repo to GitHub.
2. In Streamlit Community Cloud, create a new app from the repo.
3. Set the main file path to `app.py`.

The checked-in Streamlit config lives at `.streamlit/config.toml`.

## Notes

- This version does not use the OpenAI API.
- The app hides most Streamlit chrome inside the page, but some browser- or platform-level controls may still appear depending on Streamlit Community Cloud.
- This is still an MVP workflow app, not yet a polished product platform.
