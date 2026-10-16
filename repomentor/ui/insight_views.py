"""UI for the analysis-engine insights: data flows, module graph, debt and hotspots, clones."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from repomentor.analyzer.import_graph import to_dot
from repomentor.analyzer.taint import KIND_LABELS
from repomentor.models.analysis_result import AnalysisResult, QualityReport
from repomentor.models.issue import format_effort
from repomentor.utils.text_utils import tr_number

RATING_NOTES = {
    "A": "Borç kod büyüklüğüne göre çok düşük",
    "B": "Küçük bir temizlik yeterli",
    "C": "Planlı iyileştirme gerekiyor",
    "D": "Borç ciddi; yeni özellikten önce temizleyin",
    "E": "Borç kodun kendisinden pahalı",
}


def render_taint_flows(r: AnalysisResult) -> None:
    flows = r.security.taint_flows
    st.markdown("##### Veri akışı analizi")
    st.caption(
        f"{r.security.taint_functions} fonksiyon incelendi · kullanıcı girdisi (istek, form, URL parametresi, "
        "`st.text_input`, `input()`) değişkenler ve fonksiyonlar boyunca izlendi"
    )
    if not flows:
        st.success("Kullanıcı girdisinin tehlikeli bir çağrıya ulaştığı bir akış bulunmadı.", icon=":material/verified_user:")
        return
    st.dataframe(
        pd.DataFrame([{
            "Tür": KIND_LABELS[f.kind] + ("" if f.remote else " (yerel)"),
            "Kaynak": f"{f.source} · satır {f.source_line}",
            "Yol": " → ".join(f.path) or "doğrudan",
            "Hedef": f.sink,
            "Konum": f"{f.file}:{f.line}",
            "Fonksiyon": f.function,
        } for f in flows]),
        hide_index=True,
        alt="Kullanıcı girdisinin tehlikeli çağrılara ulaştığı doğrulanmış veri akışları",
    )
    st.caption(
        "Bu akışlar kalıp eşleştirmeyle değil, verinin kaynaktan hedefe izlenmesiyle bulundu; aynı satırdaki "
        "\"potansiyel risk\" bulgusunun yerini alırlar. `int()`, `shlex.quote()`, `html.escape()` gibi temizleyiciler izi keser."
    )


def render_import_graph(r: AnalysisResult) -> None:
    graph = r.imports
    st.markdown("##### Modül bağımlılık grafiği")
    if len(graph.modules) < 2:
        st.caption("Grafik için en az iki Python modülü gerekiyor.")
        return
    lazy = sum(e.lazy for e in graph.edges)
    st.caption(
        f"{len(graph.modules)} modül · {len(graph.edges)} import ilişkisi"
        + (f" · {lazy} tembel (fonksiyon içinde, kesikli çizgi)" if lazy else "")
        + (" · en bağlantılı 40 modül gösteriliyor" if len(graph.modules) > 40 else "")
    )
    if graph.cycles:
        st.error(
            "Döngüsel import: " + " · ".join(f"`{' → '.join(c)}`" for c in graph.cycles[:3]),
            icon=":material/sync_problem:",
        )
    # Small graphs at natural size: stretching three boxes to the column width makes them huge.
    width = "stretch" if len(graph.modules) > 12 else "content"
    st.graphviz_chart(to_dot(graph), width=width, alt="Projenin modülleri arasındaki import ilişkileri")
    coupled = [m for m in graph.modules if m.fan_in + m.fan_out][:12]
    if coupled:
        with st.expander("Bağlılık ölçütleri (Ca · Ce · kararsızlık)", icon=":material/hub:"):
            st.dataframe(
                pd.DataFrame([{"Modül": m.name, "Kullanan (Ca)": m.fan_in, "Kullandığı (Ce)": m.fan_out,
                               "Kararsızlık": m.instability} for m in coupled]),
                hide_index=True,
                column_config={"Kararsızlık": st.column_config.ProgressColumn(min_value=0.0, max_value=1.0, format="%.2f")},
                alt="Modüllerin içe ve dışa bağımlılık sayıları",
            )
            st.caption("Kararsızlık = Ce / (Ca + Ce). Çok kullanılan modüllerin (yüksek Ca) kararlı, yani düşük kararsızlıkta olması beklenir.")


def render_debt_and_hotspots(r: AnalysisResult) -> None:
    debt = r.debt
    with st.container(border=True):
        left, right = st.columns([1, 2], gap="large")
        with left:
            st.markdown("##### Teknik borç")
            st.metric(f"Bakım notu {debt.rating}", format_effort(debt.minutes),
                      help="SQALE yöntemi: bulguların düzeltme süresi / kodu yazma maliyeti (satır başına 30 dk). "
                           "A ≤ %5, B ≤ %10, C ≤ %20, D ≤ %50, E > %50.")
            st.caption(f"Borç oranı %{tr_number(debt.ratio * 100, 1)} · {RATING_NOTES[debt.rating]}")
        with right:
            st.markdown("##### Önce bu dosyalara bakın")
            if not r.hotspots:
                st.caption("Öne çıkan riskli dosya yok.")
                return
            st.dataframe(
                pd.DataFrame([{"Dosya": h.file, "Risk": h.risk, "Neden": ", ".join(h.reasons)} for h in r.hotspots[:5]]),
                hide_index=True,
                column_config={"Risk": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d")},
                alt="Bulgu, bilişsel yük ve boyuta göre en riskli dosyalar",
            )


def render_clones(q: QualityReport) -> None:
    if not q.clones:
        return
    with st.expander(f"Yapısal kopyalar ({len(q.clones)})", icon=":material/content_copy:"):
        st.caption("Sözdizimi ağacı aynı, yalnızca değişken adları veya sabit değerler farklı fonksiyonlar.")
        for clone in q.clones:
            st.markdown(f"**~{clone.lines} satır** · " + " ↔ ".join(f"`{m}`" for m in clone.members))
