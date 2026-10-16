"""Visual views: the interactive code map, attack-path diagrams and the README badge."""

from __future__ import annotations

import streamlit as st

from repomentor.analyzer.badge import badge_markdown, badge_svg
from repomentor.analyzer.code_map import COLOR_MODES, code_map_spec
from repomentor.analyzer.taint import KIND_LABELS
from repomentor.models.analysis_result import AnalysisResult, TaintFlow
from repomentor.ui.session import report_key


def render_code_map(r: AnalysisResult) -> None:
    st.markdown("##### Kod haritası")
    mode = st.segmented_control("Renk ölçüsü", list(COLOR_MODES), default="risk", format_func=lambda m: COLOR_MODES[m][0],
                                key=f"code-map-mode-{report_key()}", label_visibility="collapsed") or "risk"
    spec = code_map_spec(r, mode)
    if spec is None:
        st.caption("Haritada gösterilecek Python dosyası yok.")
        return
    st.caption("Alan: satır sayısı · renk: seçilen ölçü, :green[■] düşük → :orange[■] orta → :red[■] yüksek. "
               "Bir klasöre tıklayıp içine girin, alttaki yoldan geri dönün; ayrıntı için kutunun üzerine gelin.")
    st.echarts_chart(spec, height=460, key=f"code-map-{report_key()}-{mode}",
                     alt="Projenin dosyalarını satır sayısına göre boyutlandırıp riske göre renklendiren etkileşimli harita")


def _dot_text(text: str, limit: int = 64) -> str:
    text = text if len(text) <= limit else text[: limit - 1] + "…"
    return text.replace("\\", "\\\\").replace('"', '\\"')


def flow_dot(flow: TaintFlow) -> str:
    """Graphviz source for one confirmed flow: user input → variables / functions → dangerous call."""
    source = f"{'Kullanıcı girdisi' if flow.remote else 'Yerel girdi'}\\n{_dot_text(flow.source)}\\nsatır {flow.source_line}"
    sink = f"{KIND_LABELS[flow.kind]}\\n{_dot_text(flow.sink)}\\n{_dot_text(f'{flow.file}:{flow.line}')}"
    hops = [f'  h{i} [label="{_dot_text(hop, 40)}", fillcolor="#e9e9ee"];' for i, hop in enumerate(flow.path)]
    chain = " -> ".join(["src", *(f"h{i}" for i in range(len(flow.path))), "sink"])
    return "\n".join([
        "digraph flow {",
        '  rankdir=LR; bgcolor="transparent"; pad=0.2; nodesep=0.3;',
        '  node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=11, color="#00000030", fontcolor="#1c1d21"];',
        '  edge [color="#9a9aa5", arrowsize=0.7, penwidth=1.4];',
        f'  src [label="{source}", fillcolor="#f6dfae"];',
        *hops,
        f'  sink [label="{sink}", fillcolor="#f4b9b4"];',
        f"  {chain};",
        "}",
    ])


def render_flow_paths(r: AnalysisResult) -> None:
    flows = r.security.taint_flows
    if not flows:
        return
    st.markdown("##### Saldırı yolu")
    choice = 0
    if len(flows) > 1:
        choice = st.selectbox("Akış", range(len(flows)), key=f"flow-path-{report_key()}",
                              format_func=lambda i: f"{KIND_LABELS[flows[i].kind]} · {flows[i].file}:{flows[i].line}")
    st.graphviz_chart(flow_dot(flows[choice]), width="stretch")
    st.caption("Sarı: girdinin geldiği yer · gri: değerin geçtiği değişken ve fonksiyonlar · kırmızı: tehlikeli çağrı.")


def render_badge(r: AnalysisResult) -> None:
    st.markdown("##### README rozeti")
    st.caption("Skorunu kendi README'nde göster. Kopyaladığın satırdaki rozet shields.io üzerinden çizilir; oraya yalnızca skor gider.")
    st.image(badge_svg(r.score.overall), width="content")
    st.code(badge_markdown(r.score.overall), language="markdown", wrap_lines=True)
    st.download_button("Rozeti SVG olarak indir", badge_svg(r.score.overall), file_name="repomentor-badge.svg", mime="image/svg+xml",
                       icon=":material/workspace_premium:", key=f"badge-{report_key()}")
