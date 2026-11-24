[English](website.md) · [简体中文](zh/website.md)

# Website documentation build

Build the repository documentation into an existing landing page outside this
repository. The promotional landing page is maintained separately. Its source is
not included here. The Docs view embeds `docs/zh/`; use the documentation language
links to open English pages.

## Build

Use the existing Python environment with the project's documentation dependencies.
From the repository root on Windows, run:

```powershell
.\.venv\Scripts\python.exe scripts/build_website_docs.py --landing-dir C:\path\to\landing
```

On other systems, use the active environment:

```bash
python scripts/build_website_docs.py --landing-dir /absolute/path/to/landing
```

`--landing-dir` is required. Select an existing directory outside the repository
that contains `index.html`. The script rejects output inside the repository.
The script prints the checked output path before running MkDocs with `--strict`.
It installs no dependencies. A failed build returns a nonzero status.

## Files and navigation

`docs/` contains the maintained documentation. The documentation exporter and
`mkdocs.website.yml` remain in this repository. The configuration inherits
[the regular documentation configuration](documentation.md).
The website hook groups its navigation into usage docs, maintenance docs and API
reference. The build uses the existing Markdown pages, Python API references,
search index, code copy controls and Mermaid fences.

The website documentation theme uses a white background with blue links.
Desktop documentation keeps the category list on the left and page contents on
the right. The article scrolls independently in the center. Smaller screens use
navigation and search drawers. Maintain the landing page navigation and demo in
the external landing directory.

## Rebuild and preview

Generated files go into the external landing directory's `docs/` folder. Rebuild
with the same command after documentation or Python API changes. Keep generated
output out of the repository.

The script refuses a nonempty `docs/` directory unless it contains the script's
`.vera-website-docs` marker. Choose another landing directory if unrelated files
already occupy that path. Do not add the marker to unrelated directories.

Use Node.js 24 and the installed desktop dependencies. Run from the repository
root to preview the external landing page:

```bash
node desktop/node_modules/vite/bin/vite.js /absolute/path/to/landing --host 127.0.0.1 --port 8765 --strictPort
```

This server supports HTTP byte-range requests, which the demo video needs for
seeking. Use a static host with byte-range support when you deploy the website.

Open `http://127.0.0.1:8765/#docs`. Check the persistent top navigation, view
switching, category navigation, page contents, language links, search and code
copying. Scroll a long article and confirm that both sidebars stay in place.
Open `#demo` and check playback, seeking and fullscreen. The silent demo keeps
only these controls and pauses when you leave the view.
