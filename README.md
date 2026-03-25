# SEO Image Optimizer App

This project turns the chat-only `seo-image-optimizer` skill into a simple local application your team can run in a browser.

The app lets a user:

- upload a `.zip` of finished image exports
- enter the photographer or studio name
- enter the website URL
- enter the genre, address, and market
- choose `Auto` or `Rules-only` processing
- generate a downloadable processed zip with `hero/` and `gallery/`
- download `alt_text.csv`
- review a thumbnail chart with each new filename and its matching alt text

## What this version does

- researches the photographer website once per run
- supports hybrid processing:
  - `Auto` uses the OpenAI API when a key is present
  - `Rules-only` skips API usage entirely
- analyzes each image to generate:
  - a search-intent filename
  - a more descriptive alt text line
  - a `hero` or `gallery` assignment
- exports web-ready JPG derivatives
- packages the outputs into `processed_images.zip`

## Project structure

- [app.py](C:\Users\sara\OneDrive\Desktop\Codex\Image Seo Optimizer\app.py)
- [seo_image_optimizer/ai.py](C:\Users\sara\OneDrive\Desktop\Codex\Image Seo Optimizer\seo_image_optimizer\ai.py)
- [seo_image_optimizer/pipeline.py](C:\Users\sara\OneDrive\Desktop\Codex\Image Seo Optimizer\seo_image_optimizer\pipeline.py)
- [seo_image_optimizer/delivery.py](C:\Users\sara\OneDrive\Desktop\Codex\Image Seo Optimizer\seo_image_optimizer\delivery.py)
- [seo_image_optimizer/website_research.py](C:\Users\sara\OneDrive\Desktop\Codex\Image Seo Optimizer\seo_image_optimizer\website_research.py)

## Setup

1. Install Python 3.11 or newer.
2. Add your OpenAI API key to `.env` or paste it into the app sidebar.
3. Easiest option:

Double-click [install_and_run.bat](C:\Users\sara\OneDrive\Desktop\Codex\Image Seo Optimizer\install_and_run.bat)

4. Or run manually:

```powershell
py -3 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

On Windows, you can also double-click [run_app.bat](C:\Users\sara\OneDrive\Desktop\Codex\Image Seo Optimizer\run_app.bat).

## Notes

- This environment did not have Python, Node, or Git available, so the code was scaffolded but not executed here.
- The current implementation is a practical MVP. The next easy upgrade would be packaging it with PyInstaller so the team can launch it without touching a terminal.
- `Rules-only` mode avoids API cost, but its filenames and alt text will be more templated than `Auto` mode.
