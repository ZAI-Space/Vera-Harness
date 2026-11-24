[English](website.md) · [简体中文](zh/website.md)

# Website documentation build

Build the repository documentation into the existing landing page. The landing
page keeps its capsule navigation across Home, Docs and Demo. The Docs view embeds
`docs/zh/`; use the documentation language links to open English pages.

## Build

Use the existing Python environment with the project's documentation dependencies.
From the repository root on Windows, run:

```powershell
.\.venv\Scripts\python.exe scripts/build_website_docs.py
```

On other systems, use the active environment:

```bash
python scripts/build_website_docs.py --landing-dir /absolute/path/to/landing
```

The default landing directory is the repository's `website/`. Use `--landing-dir`
to build beside an external landing page that contains `index.html`.
Within the repository, the script permits output only in `website/docs/`.
The script prints the checked output path before running MkDocs with `--strict`.
It installs no dependencies. A failed build returns a nonzero status.

## Files and navigation

`docs/` contains the maintained documentation; `website/` contains the static
landing page source. `mkdocs.website.yml` inherits
[the regular documentation configuration](documentation.md).
The website hook groups its navigation into usage docs, maintenance docs and API
reference. The build uses the existing Markdown pages, Python API references,
search index, code copy controls and Mermaid fences.

The website theme uses a white background with blue links. The landing page slides
between its Home, Docs and Demo views without replacing the top navigation.
Desktop documentation keeps the category list on the left and page contents on
the right. The article scrolls independently in the center. Smaller screens use
navigation and search drawers. The original seven Home sections remain available.

## Rebuild and preview

Generated files go into the landing directory's `docs/` folder. The default
`website/docs/` output is ignored by Git. Rebuild with the
same command after documentation or Python API changes. Keep generated output
out of the repository.

The script refuses a nonempty `docs/` directory unless it contains the script's
`.vera-website-docs` marker. Choose another landing directory if unrelated files
already occupy that path. Do not add the marker to unrelated directories.

Serve the whole landing directory to test relative links and search:

```bash
python -m http.server 8765 --directory /absolute/path/to/landing
```

Open `http://127.0.0.1:8765/#docs`. Check the persistent top navigation, view
switching, category navigation, page contents, language links, search and code
copying. Scroll a long article and confirm that both sidebars stay in place.
