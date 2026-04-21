# memgov

Human-annotated meeting archive for public bodies (starting with Memphis City Council).

## Goals

- Ingest YouTube meeting videos and transcripts.
- Support local, chunk-by-chunk human annotation (summary, tags, mentions, votes).
- Generate a minimalist static site (no client-side JS) for GitHub Pages.
- Keep architecture reusable for other bodies (county/school boards).

## Project Layout

- `scripts/ingest_youtube.py`: fetches metadata + transcript, creates meeting JSON and starter annotation.
- `admin/`: local annotation UI (JS-heavy, not deployed).
- `scripts/build_site.py`: compiles processed + annotation data into `docs/` static pages.
- `site/templates/`: Jinja templates.
- `site/static/style.css`: tiny CSS for deployed pages.
- `data/processed/meetings/`: meeting transcript chunks.
- `data/annotations/meetings/`: human annotations.

## Quick Start

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Ingest a YouTube meeting:

```bash
python scripts/ingest_youtube.py "https://www.youtube.com/watch?v=VIDEO_ID" --date 2026-04-02
```

4. Annotate locally:

```bash
python -m http.server 8000
```

Then open:

- `http://localhost:8000/admin/index.html`

Load the generated meeting JSON from `data/processed/meetings/` and optionally existing annotation JSON from `data/annotations/meetings/`.
Download the updated annotation and place it in `data/annotations/meetings/MEETING_ID.json`.

5. Build static site:

```bash
python scripts/build_site.py
```

6. Publish `docs/` to GitHub Pages.

## Notes

- Static output is intentionally content-first and minimalist.
- Deployable pages are plain HTML + CSS only.
- Admin tool can use rich JS because it stays local.
