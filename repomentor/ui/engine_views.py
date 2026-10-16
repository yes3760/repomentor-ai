"""UI for the call graph, control flow, data-science checks, README commands and the fix patch."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from repomentor.analyzer.rules import SHORT_LABELS
from repomentor.models.analysis_result import AnalysisResult, UnusedSymbol
from repomentor.ui.components import safe_md
from repomentor.ui.session import report_key
from repomentor.utils.text_utils import share_percent

KIND_NAMES = {"function": "fonksiyon", "method": "metot", "class": "sınıf"}
PATCH_NAME = "repomentor-fixes.patch"


def _plain(text: str) -> str:
    return text.replace("`", "")


def _table(rows: list[dict], alt: str) -> None:
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", alt=alt)


def _symbols(symbols: list[UnusedSymbol]) -> list[dict]:
    return [{"Sembol": s.name, "Tür": KIND_NAMES.get(s.kind, s.kind), "Konum": f"{s.file}:{s.line}"} for s in symbols]


def render_code_health(r: AnalysisResult) -> None:
    """Dead code (call graph) and control-flow findings side by side."""
    left, right = st.columns(2, gap="medium")
    with left:
        st.markdown("##### Kullanılmayan kod")
        st.caption(f"Çağrı grafiği · {r.usage.symbols} sembol, {r.usage.references} referans")
        if r.usage.unused:
            _table(_symbols(r.usage.unused), "Hiçbir giriş noktasından ulaşılamayan fonksiyon ve sınıflar")
        else:
            st.success("Her fonksiyona ve sınıfa bir giriş noktasından ulaşılıyor.", icon=":material/account_tree:")
    with right:
        st.markdown("##### Kontrol akışı")
        st.caption("Fonksiyon başına kontrol akış grafiği · erişilemeyen satırlar, her yolda kapatılmayan dosya / bağlantılar")
        if r.quality.flow:
            _table([{"Bulgu": SHORT_LABELS[f.rule], "Konum": f"{f.file}:{f.line}", "Fonksiyon": f.function, "Ayrıntı": _plain(f.detail)}
                    for f in r.quality.flow], "Erişilemeyen kod ve kapatılmayan kaynaklar")
        else:
            st.success("Erişilemeyen kod veya kapatılmayan kaynak bulunmadı.", icon=":material/alt_route:")


def render_data_science(r: AnalysisResult) -> None:
    ds = r.data_science
    if not ds.applicable:
        return
    st.markdown("##### Veri bilimi kontrolleri")
    st.caption("pandas / scikit-learn kodu satır sırasıyla izlendi: veri bölünmeden önce öğrenen adımlar, test verisine `fit`, yavaş pandas kalıpları")
    if not ds.findings:
        st.success("Veri sızıntısı veya yavaş pandas kalıbı bulunmadı.", icon=":material/query_stats:")
        return
    leaks = sum(f.rule.startswith("LEAK") for f in ds.findings)
    if leaks:
        st.error(f"{leaks} veri sızıntısı: modelin ölçülen başarısı gerçek veride tutmayabilir.", icon=":material/water_drop:")
    _table([{"Bulgu": SHORT_LABELS[f.rule], "Konum": f"{f.file}:{f.line}", "Ayrıntı": _plain(f.detail)} for f in ds.findings],
           "Veri sızıntısı ve pandas anti-pattern bulguları")


def render_test_reach(r: AnalysisResult) -> None:
    usage = r.usage
    if usage.test_reach is None:
        return
    st.markdown("##### Testlerin ulaştığı kod (statik)")
    st.progress(usage.test_reach, text=f"%{share_percent(usage.test_reach)} · {usage.test_reached}/{usage.test_total} fonksiyona "
                                       "testlerden bir çağrı zinciriyle ulaşılıyor")
    st.caption("Testler çalıştırılmadan çağrı grafiğinden hesaplanır. Satır kapsamı (coverage.py) değildir; "
               "hiçbir testin çağırmadığı fonksiyonları gösterir.")
    if usage.untested:
        with st.expander(f"Hiçbir testin ulaşmadığı fonksiyonlar ({len(usage.untested)})", icon=":material/science:"):
            _table(_symbols(usage.untested), "Testlerden ulaşılamayan public fonksiyonlar")


def render_readme_commands(r: AnalysisResult) -> None:
    d = r.documentation
    if not d.commands_checked:
        return
    st.markdown("##### README komutları")
    st.caption(f"{d.commands_checked} komut proje dosyalarına karşı kontrol edildi (hiçbiri çalıştırılmadı)")
    if d.broken_commands:
        _table([{"Komut": b.command, "Sorun": _plain(b.problem), "README satırı": b.line} for b in d.broken_commands],
               "README'de çalışmayacak komutlar")
    else:
        st.success("README'deki komutlar projeyle uyumlu.", icon=":material/terminal:")


def patch_download(r: AnalysisResult, place: str, **kwargs) -> None:
    st.download_button("Düzeltme yaması (.patch)", r.fixes.patch, file_name=PATCH_NAME, mime="text/x-diff",
                       icon=":material/healing:", key=f"patch-{place}-{report_key()}", **kwargs)


def render_fixes(r: AnalysisResult) -> None:
    fixes = r.fixes
    if not fixes.files:
        return
    with st.container(border=True):
        st.markdown("##### Otomatik düzeltme yaması")
        st.caption(f"{fixes.change_count} güvenli değişiklik · {len(fixes.files)} dosya. Proje dosyalarına dokunulmadı: "
                   f"yamayı inceleyin, sonra proje klasöründe `git apply {PATCH_NAME}` ile uygulayın.")
        patch_download(r, "roadmap", type="primary")
        for fix in fixes.files:
            with st.expander(fix.path + (" · yeni dosya" if fix.new_file else ""), icon=":material/difference:"):
                st.markdown("\n".join(f"- {safe_md(change)}" for change in fix.changes))
                st.code(fix.diff, language="diff")
