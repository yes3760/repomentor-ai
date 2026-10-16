"""The RepoMentor logo, bundled locally for offline use.

Two versions of the artwork are shipped: a light wordmark for dark backgrounds
and a dark one for light backgrounds. The app embeds both and shows the one that
suits the background (see `.rm-logo-on-light` / `.rm-logo-on-dark` in styles):
Streamlit sets `color-scheme` on `.stApp`, so the choice follows a theme change
at once, without a rerun.
"""

from __future__ import annotations

import base64
import io
from functools import lru_cache
from pathlib import Path

from PIL import Image

ASSETS = Path(__file__).resolve().parents[2] / "assets"
LOGO_PATH = ASSETS / "repomentor-logo.png"              # light wordmark: dark backgrounds
LOGO_LIGHT_PATH = ASSETS / "repomentor-logo-light.png"  # dark wordmark: light backgrounds
ICON_PATH = ASSETS / "repomentor-icon.png"              # the R mark alone, for the browser tab
EMBED_WIDTH = 888                                        # 2× the sidebar width, after the logo's zoom


@lru_cache(maxsize=None)
def _data_uri(path: Path) -> str:
    """The artwork scaled to what the sidebar can show, so each page does not carry 1774 px images."""
    image = Image.open(path)
    image = image.resize((EMBED_WIDTH, round(image.height * EMBED_WIDTH / image.width)), Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def logo_html(class_name: str = "rm-logo") -> str:
    return (
        f'<div class="{class_name}" role="img" aria-label="RepoMentor">'
        f'<img class="rm-logo-img rm-logo-on-light" src="{_data_uri(LOGO_LIGHT_PATH)}" alt="">'
        f'<img class="rm-logo-img rm-logo-on-dark" src="{_data_uri(LOGO_PATH)}" alt="">'
        "</div>"
    )
