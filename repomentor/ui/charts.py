"""Altair charts. Magnitude only, so one hue (or an ordinal ramp of it), thin bars,
rounded data ends, recessive axes, a tooltip on every mark."""

from __future__ import annotations

import altair as alt
import pandas as pd

# The supplied logo's gold → orange → magenta palette.
ORDINAL_BRAND = ["#e6af49", "#e58932", "#d65753", "#ad3c84"]
BAR_BRAND = "#dd8a35"
BANDS = ["Düşük (1-5)", "Orta (6-10)", "Yüksek (11-20)", "Çok yüksek (21+)"]


def complexity_chart(distribution: dict[str, int]) -> alt.Chart:
    df = pd.DataFrame({"Karmaşıklık": BANDS, "Fonksiyon": [distribution.get(b, 0) for b in BANDS]})
    base = alt.Chart(df).encode(
        x=alt.X("Karmaşıklık:N", sort=BANDS, title=None, axis=alt.Axis(labelAngle=0, labelLimit=140)),
        y=alt.Y("Fonksiyon:Q", title="Fonksiyon sayısı", axis=alt.Axis(tickMinStep=1, grid=True, gridOpacity=0.25)),
        tooltip=[alt.Tooltip("Karmaşıklık:N", title="Bant"), alt.Tooltip("Fonksiyon:Q", title="Fonksiyon")],
    )
    bars = base.mark_bar(size=44, cornerRadiusTopLeft=6, cornerRadiusTopRight=6).encode(
        color=alt.Color("Karmaşıklık:N", sort=BANDS, scale=alt.Scale(domain=BANDS, range=ORDINAL_BRAND), legend=None),
    )
    labels = base.mark_text(dy=-8, fontSize=12, fontWeight=600).encode(text="Fonksiyon:Q")
    return (bars + labels).properties(height=240, background="transparent").configure_view(strokeWidth=0)


def language_chart(languages: dict[str, int], limit: int = 7) -> alt.Chart:
    items = list(languages.items())
    if len(items) > limit:
        items = items[: limit - 1] + [("Diğer", sum(v for _, v in items[limit - 1:]))]
    df = pd.DataFrame(items, columns=["Dil", "Satır"])
    order = df["Dil"].tolist()
    base = alt.Chart(df).encode(
        y=alt.Y("Dil:N", sort=order, title=None, axis=alt.Axis(labelLimit=160)),
        x=alt.X("Satır:Q", title="Satır sayısı", axis=alt.Axis(grid=True, gridOpacity=0.25)),
        tooltip=[alt.Tooltip("Dil:N"), alt.Tooltip("Satır:Q", format=",")],
    )
    bars = base.mark_bar(size=18, color=BAR_BRAND, cornerRadiusTopRight=5, cornerRadiusBottomRight=5)
    labels = base.mark_text(align="left", dx=6, fontSize=12, fontWeight=600).encode(text=alt.Text("Satır:Q", format=","))
    # 44 px for the x axis plus 40 px per language keeps labels apart even with one or two rows.
    return (bars + labels).properties(height=44 + 40 * max(len(df), 2), background="transparent").configure_view(strokeWidth=0)
