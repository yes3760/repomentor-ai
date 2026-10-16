"""The project as an interactive map: folders and files as nested rectangles.

Rectangle area is the file's size in lines; colour is one of three measures,
each already on a 0-100 scale so the colours mean the same in every project:
the hotspot risk, the cognitive-load percentile or the findings percentile.
Every rectangle carries a ready-made tooltip, because ECharts options must be
plain JSON (no formatter callbacks). Repository text is HTML-escaped before it
reaches the tooltip.
"""

from __future__ import annotations

from html import escape
from pathlib import PurePosixPath

from repomentor.analyzer.insights import base_path, file_risks
from repomentor.models.analysis_result import AnalysisResult
from repomentor.models.issue import Issue

# label, how a file's row turns into 0-100
COLOR_MODES = {
    "risk": ("Risk", lambda row: row["risk"]),
    "cognitive": ("Bilişsel yük", lambda row: round(100 * row["ranks"]["cognitive"])),
    "issues": ("Bulgular", lambda row: round(100 * row["ranks"]["issues"])),
}
STOPS = ((0, (63, 166, 120)), (50, (224, 168, 59)), (100, (214, 69, 80)))   # green → amber → red


def heat_color(value: float) -> str:
    """Colour on the green → amber → red scale for a 0-100 value."""
    value = max(0.0, min(100.0, float(value)))
    for (low, start), (high, end) in zip(STOPS, STOPS[1:], strict=False):
        if value <= high:
            share = (value - low) / (high - low)
            return "#" + "".join(f"{round(a + (b - a) * share):02x}" for a, b in zip(start, end, strict=True))
    return "#" + "".join(f"{c:02x}" for c in STOPS[-1][1])


def _titles_by_file(issues: list[Issue]) -> dict[str, list[str]]:
    titles: dict[str, list[str]] = {}
    for issue in sorted(issues, key=lambda i: i.sort_key):
        for path in {base_path(loc.file) for loc in issue.locations}:
            titles.setdefault(path, []).append(issue.title.replace("`", ""))
    return titles


def _tooltip(path: str, row: dict, titles: list[str]) -> str:
    severe = f" ({row['severe']} kritik/yüksek)" if row["severe"] else ""
    lines = [
        f"<b>{escape(path)}</b>",
        f"{row['lines']} satır · {row['functions']} fonksiyon",
        f"Risk {row['risk']}/100 · bilişsel yük {row['cognitive']}",
        f"{row['count']} bulgu{severe}" if row["count"] else "Bulgu yok",
    ]
    lines += [f"• {escape(title[:70])}" for title in titles[:3]]
    return "<br/>".join(lines)


def _leaf(path: str, row: dict, titles: list[str], mode: str) -> dict:
    value = COLOR_MODES[mode][1](row)
    return {
        "name": PurePosixPath(path).name, "value": max(row["lines"], 1), "path": path, "heat": value,
        "itemStyle": {"color": heat_color(value)},
        "tooltip": {"formatter": _tooltip(path, row, titles)},
    }


def _insert(tree: dict, path: str, leaf: dict) -> None:
    node = tree
    for folder in PurePosixPath(path).parts[:-1]:
        node = node.setdefault(folder, {})
    node[leaf["name"]] = leaf


def _children(tree: dict) -> list[dict]:
    """Folders before files, biggest first; a folder's area is the sum of its files."""
    nodes = []
    for name, child in tree.items():
        if "path" in child and "value" in child:
            nodes.append(child)
        else:
            kids = _children(child)
            nodes.append({"name": name, "value": sum(k["value"] for k in kids), "children": kids,
                          "tooltip": {"formatter": f"<b>{escape(name)}/</b><br/>{sum(k['value'] for k in kids)} satır"}})
    return sorted(nodes, key=lambda n: -n["value"])


def code_map_spec(result: AnalysisResult, mode: str = "risk") -> dict | None:
    """ECharts treemap option for the project's source files, or None when there is nothing to draw."""
    rows = file_risks(result.quality, result.issues)
    if not rows:
        return None
    titles = _titles_by_file(result.issues)
    tree: dict = {}
    for path, row in rows.items():
        _insert(tree, path, _leaf(path, row, titles.get(path, []), mode))
    return {
        "tooltip": {"confine": True, "enterable": False},
        "series": [{
            "type": "treemap", "name": result.project.name, "data": _children(tree),
            "roam": False, "nodeClick": "zoomToNode", "squareRatio": 1.2, "top": 4, "left": 2, "right": 2, "bottom": 34,
            "breadcrumb": {"show": True, "bottom": 2, "itemStyle": {"color": "rgba(128,128,128,0.25)"}},
            "label": {"show": True, "formatter": "{b}", "fontSize": 11, "overflow": "truncate"},
            "upperLabel": {"show": True, "height": 20, "fontSize": 11},
            "itemStyle": {"borderColor": "rgba(0,0,0,0.25)", "borderWidth": 1, "gapWidth": 1},
            "levels": [
                {"itemStyle": {"borderWidth": 0, "gapWidth": 3}},
                {"itemStyle": {"borderWidth": 2, "gapWidth": 2, "borderColor": "rgba(128,128,128,0.35)"}},
                {"itemStyle": {"borderWidth": 1, "gapWidth": 1}},
            ],
        }],
    }
