"""RepoMentor AI workspace. Run with: streamlit run app.py"""

from __future__ import annotations

from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from repomentor.analyzer.pipeline import analyze_project
from repomentor.analyzer.repository_loader import LoaderError, load_github, load_local, load_zip
from repomentor.ui.branding import LOGO_PATH, logo_html
from repomentor.ui.components import esc
from repomentor.ui.session import remember_result
from repomentor.ui.sidebar import render_sidebar
from repomentor.ui.styles import css
from repomentor.ui.views import render_result
from repomentor.utils.constants import APP_NAME, APP_VERSION, MAX_ARCHIVE_BYTES

load_dotenv()
EXAMPLES_DIR = Path(__file__).parent / "examples"
EXAMPLES = {
    "clean_project": ("task-api", "FastAPI · SQLite · pytest", "Testler, Docker ve CI ile tamamlanmış bir API.", "Testli", "good"),
    "medium_project": ("film-recommender", "Streamlit · scikit-learn", "Çalışan uygulama, sınırlı test ve dokümantasyon.", "Kısmi kapsam", "warning"),
    "problematic_project": ("flask-notes", "Flask · SQLite", "Açık anahtar, SQL/eval enjeksiyonu, kapatılmayan bağlantı ve ölü kod içeren örnek.", "Riskli kod", "critical"),
    "ml_project": ("churn-model", "pandas · scikit-learn", "Veri sızıntısı ve yavaş pandas kalıpları içeren model eğitimi.", "Veri sızıntısı", "warning"),
    "notebook_project": ("churn-notebook", "Jupyter · pandas · scikit-learn", "Hücreler arasında veri sızıntısı olan keşif notebook'u.", "Notebook", "warning"),
}

st.set_page_config(page_title=APP_NAME, page_icon=str(LOGO_PATH), layout="wide", initial_sidebar_state="expanded")
st.html(css())


def header() -> None:
    st.html(f'<div class="rm-mobile-brand">{logo_html()}</div>')
    st.html('''<div class="rm-topbar"><div class="rm-breadcrumb">İncelemeler <span>/</span> Yeni inceleme</div>
      <span class="rm-top-meta">Python projeleri · Statik AST Denetimi</span></div>
      <section class="rm-hero-banner">
        <div class="rm-page-kicker">KOD KALİTESİ &amp; GÜVENLİK DENETİMİ</div>
        <h1>Yeni inceleme<span class="rm-title-period">.</span></h1>
        <p>Bir GitHub deposu veya ZIP arşivi ekle; kod kalitesini, güvenlik risklerini, test kapsamını ve mimari eksikleri tek raporda incele.</p>
        <div class="rm-workflow-strip">
          <div class="rm-workflow-step"><span class="rm-workflow-num">01</span>
            <div class="rm-workflow-text">Depoyu Bağla<small>GitHub URL, dal veya ZIP arşivi</small></div></div>
          <div class="rm-workflow-step"><span class="rm-workflow-num">02</span>
            <div class="rm-workflow-text">AST &amp; Güvenlik Taraması<small>Radon · Ruff · Bandit · Gizli anahtar</small></div></div>
          <div class="rm-workflow-step"><span class="rm-workflow-num">03</span>
            <div class="rm-workflow-text">Skor &amp; Yol Haritası<small>Önceliklendirilmiş aksiyon planı ve AI yorumu</small></div></div>
        </div>
      </section>''')


def run(loader, llm) -> None:
    progress = st.progress(0.0, text="Proje hazırlanıyor…")
    try:
        with st.status("Proje hazırlanıyor…", expanded=True) as status:
            def report(message: str, fraction: float) -> None:
                status.update(label=message)
                progress.progress(fraction, text=message)

            with loader as loaded:
                result = analyze_project(
                    loaded, llm=llm, progress=report, check_dependencies=st.session_state.get("osv-enabled", True)
                )
            remember_result(result)
            status.update(label="Analiz tamamlandı", state="complete", expanded=False)
    except LoaderError as exc:
        progress.empty()
        st.error(str(exc), icon=":material/error:")
        return
    progress.empty()
    st.rerun()


def input_area(llm) -> None:
    with st.container(border=True, key="source-panel"):
        st.html('''<div class="rm-panel-heading"><span class="rm-panel-index">01 / KAYNAK SEÇİMİ</span>
          <h2>Depoyu ekle</h2></div>''')
        github_tab, zip_tab = st.tabs(["GitHub", "ZIP dosyası"])
        with github_tab:
            with st.form("github", border=False):
                field, action = st.columns([3, 1.65], vertical_alignment="bottom")
                with field:
                    url = st.text_input("Depo adresi", placeholder="github.com/kullanici/proje")
                with action:
                    submitted = st.form_submit_button("Projeyi analiz et", type="primary", width="stretch")
                if submitted:
                    if url.strip():
                        run(load_github(url), llm)
                    else:
                        st.error("Başlamak için GitHub depo bağlantısını gir.")
            st.caption("Herkese açık depolar, dal (branch) bağlantıları ve alt klasörler desteklenir.")
        with zip_tab:
            upload = st.file_uploader(
                "Proje arşivi", type=["zip"], max_upload_size=MAX_ARCHIVE_BYTES // (1024 * 1024),
                help="En fazla 50 MB. .venv ve node_modules klasörlerini eklemene gerek yok.",
            )
            if st.button("ZIP dosyasını analiz et", type="primary", key="zip-run", disabled=upload is None,
                         width="stretch"):
                run(load_zip(upload.getvalue(), upload.name), llm)
        st.html('''<div class="rm-source-note"><span class="rm-note-marker">✓</span>
          <p>Kaynak kod asla çalıştırılmaz; yalnızca AST ile ayrıştırılır ve geçici dosyalar analiz sonunda otomatik silinir.</p></div>''')


def demos(llm) -> None:
    st.html('''<div class="rm-section-heading"><h2>Örnek depolar</h2>
      <span>Kendi projen olmadan tek tıkla dene</span></div>''')
    with st.container(border=False, key="examples-list"):
        for key, (name, tech, description, status, tone) in EXAMPLES.items():
            chips = "".join(f'<span class="rm-repo-chip">{t.strip()}</span>' for t in tech.split("·"))
            with st.container(border=False, key=f"demo-{key}"):
                info, action = st.columns([5.5, 1.2], vertical_alignment="center")
                with info:
                    st.html(
                        f'<div class="rm-repository-row"><span class="rm-repo-symbol" aria-hidden="true">⌘</span>'
                        f'<div class="rm-repository-copy"><div class="rm-repository-title"><b>{name}</b>'
                        f'<span class="rm-repo-status" style="border:1px solid color-mix(in srgb, var(--rm-{tone}) 38%, transparent);'
                        f'background:color-mix(in srgb, var(--rm-{tone}) 12%, transparent)">'
                        f'<i style="background:var(--rm-{tone})"></i>{status}</span></div>'
                        f'<p>{description}</p><div class="rm-repo-chips">{chips}</div></div></div>'
                    )
                with action:
                    clicked = st.button("İncele", key=f"demo-{key}-run", icon=":material/arrow_forward:", width="stretch")
                if clicked:   # full width under the row, not inside the narrow button column
                    run(load_local(EXAMPLES_DIR / key, source="demo"), llm)


def scope() -> None:
    checks = [
        ("Kod kalitesi", "AST · Radon · Ruff", 25),
        ("Güvenlik", "Gizli anahtarlar · Bandit", 25),
        ("Test yapısı", "Testler · CI yapılandırması", 15),
        ("Dokümantasyon", "README · Docstring", 15),
        ("Proje düzeni", "Modüller · Bağımlılıklar", 10),
        ("Çalıştırılabilirlik", "Giriş noktası · Docker", 10),
    ]
    rows = "".join(
        f'<div class="rm-scope-row">'
        f'<div class="rm-scope-row-top"><span class="rm-scope-number">{index:02d}</span>'
        f'<b>{title}</b><span class="rm-scope-weight">%{weight}</span></div>'
        f'<p>{tools}</p>'
        f'<div class="rm-scope-bar"><span style="width:{weight * 4}%"></span></div>'
        f'</div>'
        for index, (title, tools, weight) in enumerate(checks, 1)
    )
    st.html(f'''<aside class="rm-scope"><div class="rm-panel-index">02 / PUANLAMA MODELİ</div>
      <h2>Analiz kapsamı</h2>{rows}
      <div class="rm-scope-foot"><span class="rm-small-mark">RM</span><p>Skor tamamen deterministik statik ölçümlerden hesaplanır.<br>Yapay zekâ yorumu skoru değiştirmez.</p></div></aside>''')


def main() -> None:
    llm = render_sidebar()
    result = st.session_state.get("result")
    if result is not None and st.session_state.get("view") == "report":
        render_result(result)
    else:
        header()
        left, right = st.columns([1.85, 1], gap="large")
        with left:
            input_area(llm)
            demos(llm)
            if result is not None:
                st.button("Son rapora dön", on_click=lambda: st.session_state.update(view="report"), icon=":material/history:")
        with right:
            scope()
    st.html(f'''<footer class="rm-footer"><span>RepoMentor <span class="rm-version">v{esc(APP_VERSION)}</span></span>
      <span>Python · Statik Kod Kalitesi ve Güvenlik Denetimi</span></footer>''')


if __name__ == "__main__":
    main()
