[English](licenses.md) · [简体中文](zh/licenses.md)

# Licenses and fonts

VERA-owned code uses the repository MIT license. Third-party code retains its own terms. Renaming the product does not remove attribution duties. See root `THIRD_PARTY_NOTICES.md` and `desktop/third_party/`.

| Material | Source and license | Distribution requirement |
| --- | --- | --- |
| Base Agent source | mini-swe-agent, MIT | Retain copyright/license text; old command/config reads are compatibility paths. |
| Desktop base | Percho, MIT | Retain source attribution and license. |
| Parts of plugin/schedule UI | PI-Desktop, LGPL-3.0 | Preserve applicable source, modifications and LGPL notices; do not relabel as MIT. |
| Mathematical fonts | KaTeX, MIT | Commercial use and distribution permitted with copyright and license notices. |
| Editor icon font | Microsoft Codicons, CC BY 4.0 | Commercial use permitted with attribution, license link and change notices. |
| Editor and dependencies | Monaco and package LICENSE/ThirdPartyNotices | Preserve the notices for the actual distributed versions. |

## Packaging

Body text uses the system font stack. The application does not redistribute system font binaries. Naming a system font in CSS does not grant redistribution rights.

Keep all KaTeX mathematical families. The Electron build retains WOFF2 and removes duplicate WOFF/TTF formats. Keep Monaco's Codicon TTF: it supplies editor icons. MkDocs disables remote Google font loading.

Ship `desktop/third_party/katex-LICENSE`, `codicons-LICENSE` and Monaco's license/third-party notices with desktop distributions. Check the pinned source license before adding fonts, artwork, plugins or upstream code. A package-level license field may not describe every embedded asset.

Sources: [KaTeX fonts](https://github.com/KaTeX/katex-fonts/blob/master/LICENSE), [Codicons](https://github.com/microsoft/vscode-codicons/blob/main/LICENSE).

## Landing page fonts

The static landing page loads Inter, Quantico, Space Grotesk and JetBrains Mono
from Google Fonts. These families use SIL Open Font License 1.1 and permit
commercial use. The repository contains no landing page font binaries. If you
self-host these fonts, include their copyright and OFL notices and follow the
reserved-name conditions. Remote fonts require access to Google Fonts; local
fallback fonts remain available when the service cannot be reached.

Font licenses: [Inter](https://github.com/google/fonts/blob/main/ofl/inter/OFL.txt),
[Quantico](https://github.com/google/fonts/blob/main/ofl/quantico/OFL.txt),
[Space Grotesk](https://github.com/google/fonts/blob/main/ofl/spacegrotesk/OFL.txt),
[JetBrains Mono](https://github.com/google/fonts/blob/main/ofl/jetbrainsmono/OFL.txt).
