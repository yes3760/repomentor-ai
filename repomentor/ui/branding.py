"""The supplied RepoMentor logo, bundled locally for offline use."""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

LOGO_PATH = Path(__file__).resolve().parents[2] / "assets" / "repomentor-logo.png"


@lru_cache(maxsize=1)
def logo_uri() -> str:
    return "data:image/png;base64," + base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")


def logo_html(class_name: str = "rm-brand-logo") -> str:
    return f'<img class="{class_name}" src="{logo_uri()}" alt="RepoMentor" width="1774" height="887">'
