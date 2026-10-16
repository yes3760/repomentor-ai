"""A README badge for the score: a shields.io link to paste, and a self-contained SVG to download."""

from __future__ import annotations

from html import escape

PROJECT_URL = "https://github.com/yes3760/repomentor-ai"
LABEL = "RepoMentor AI"
# (minimum score, shields.io colour name, hex for the local SVG)
COLORS = ((90, "brightgreen", "#4c1"), (75, "green", "#97ca00"), (60, "yellow", "#dfb317"), (0, "orange", "#fe7d37"))


def _color(score: int) -> tuple[str, str]:
    return next((name, hex_) for limit, name, hex_ in COLORS if score >= limit)


def badge_markdown(score: int) -> str:
    """Markdown for a README; shields.io receives only the label, the score and a colour."""
    name, _ = _color(score)
    return f"[![{LABEL}: {score}/100](https://img.shields.io/badge/RepoMentor_AI-{score}%2F100-{name})]({PROJECT_URL})"


def _width(text: str) -> int:
    """Rough Verdana 11px advance: wide enough for digits and capitals, no font file needed."""
    return round(sum(7.5 if c.isupper() or c.isdigit() else 3.5 if c in " /.:" else 6.2 for c in text)) + 12


def badge_svg(score: int) -> str:
    """A flat badge in the shields.io style, usable without any network request."""
    message = f"{score}/100"
    left, right = _width(LABEL), _width(message)
    total = left + right
    _, color = _color(score)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total}" height="20" role="img" aria-label="{escape(LABEL)}: {message}">'
        f'<title>{escape(LABEL)}: {message}</title>'
        f'<linearGradient id="s" x2="0" y2="100%"><stop offset="0" stop-color="#bbb" stop-opacity=".1"/><stop offset="1" stop-opacity=".1"/></linearGradient>'
        f'<clipPath id="r"><rect width="{total}" height="20" rx="3" fill="#fff"/></clipPath>'
        f'<g clip-path="url(#r)"><rect width="{left}" height="20" fill="#555"/><rect x="{left}" width="{right}" height="20" fill="{color}"/>'
        f'<rect width="{total}" height="20" fill="url(#s)"/></g>'
        f'<g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11">'
        f'<text x="{left / 2}" y="14">{escape(LABEL)}</text><text x="{left + right / 2}" y="14">{message}</text></g></svg>'
    )
