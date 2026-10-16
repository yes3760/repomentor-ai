"""Sidebar: choose a free LLM provider (or none) and show the privacy notes."""

from __future__ import annotations

import streamlit as st

from repomentor.ai.providers import PROVIDERS, LLMConfig, list_models, model_size_billions, ollama_available, resolve_api_key
from repomentor.ui.branding import logo_html
from repomentor.ui.session import HISTORY_LIMIT, clear_history, new_analysis, open_report

RECOMMENDED_OLLAMA = PROVIDERS["ollama"].default_model


@st.cache_data(ttl=300, show_spinner=False)
def _remote_models(provider: str, api_key: str) -> list[str]:
    """Cloud model lists change rarely and cost a network round trip; Ollama is asked live instead,
    so a model pulled or a server started a moment ago shows up on the next click."""
    return list_models(provider, api_key)


def _default_provider() -> str:
    if ollama_available():
        return "ollama"
    return next((p for p in PROVIDERS if PROVIDERS[p].needs_key and resolve_api_key(p)), "ollama")


def _retry_button() -> None:
    st.button("Yeniden dene", icon=":material/refresh:", key="ollama-retry", width="stretch")


def _ollama_config() -> LLMConfig | None:
    if not ollama_available():
        st.error("Ollama çalışmıyor. [Ollama'yı indirin](https://ollama.com/download), uygulamayı açın ve yeniden deneyin.",
                 icon=":material/power_off:")
        _retry_button()
        return None
    models = list_models("ollama")
    if not models:
        st.warning(f"Ollama'da yüklü model yok. Terminalde `ollama pull {RECOMMENDED_OLLAMA}` çalıştırıp yeniden deneyin.",
                   icon=":material/download:")
        _retry_button()
        return None
    model = st.selectbox("Model", models, key="ollama-model", help="Bilgisayarınızdaki Ollama modelleri; önerilenler başta.")
    if RECOMMENDED_OLLAMA not in models and (model_size_billions(model) or 7) < 7:
        st.caption(f"Küçük modeller daha zayıf yorum yapar. Daha isabetli sonuç için `ollama pull {RECOMMENDED_OLLAMA}` (~4,7 GB).")
    st.caption("Yerel modelde yorum 1–2 dakika sürebilir.")
    return LLMConfig(provider="ollama", model=model)


def _api_key(provider: str) -> str | None:
    spec = PROVIDERS[provider]
    if key := resolve_api_key(provider):
        st.caption("Anahtar sunucu ayarlarından alındı.")
        return key
    key = st.text_input("API anahtarı", type="password", key=f"api-key-{provider}", placeholder="Anahtarı buraya yapıştırın",
                        help="Yalnızca bu oturumda kullanılır, kaydedilmez.")
    st.caption(f"[Ücretsiz anahtar al →]({spec.signup_url})")
    return key.strip() or None


def _cloud_config(provider: str) -> LLMConfig | None:
    api_key = _api_key(provider)
    if not api_key:
        st.info("Anahtar girilene kadar analiz kural tabanlı yapılır.", icon=":material/key:")
        return None
    models = _remote_models(provider, api_key)
    if models:
        model = st.selectbox("Model", models, key=f"model-{provider}",
                             help="Liste sağlayıcıdan canlı alınır; yalnızca ücretsiz modeller gösterilir.")
    else:
        st.warning("Model listesi alınamadı: anahtar hatalı olabilir ya da servis şu an yanıt vermiyor.", icon=":material/warning:")
        model = st.text_input("Model", value=PROVIDERS[provider].default_model, key=f"model-name-{provider}")
    return LLMConfig(provider=provider, model=model, api_key=api_key)


def _ai_settings() -> LLMConfig | None:
    enabled = st.toggle("Yapay zekâ yorumunu ekle", value=False, key="ai-enabled",
                        help="İsteğe bağlıdır. Kural tabanlı skor ve rapor yapay zekâ olmadan da çalışır.")
    if not enabled:
        st.caption("Özet ve mimari değerlendirme ekler.")
        return None
    if "ai-provider" not in st.session_state:
        st.session_state["ai-provider"] = _default_provider()
    provider = st.selectbox("Sağlayıcı", list(PROVIDERS), key="ai-provider", format_func=lambda key: PROVIDERS[key].label)
    st.caption(PROVIDERS[provider].note)
    return _ollama_config() if provider == "ollama" else _cloud_config(provider)


def render_sidebar() -> LLMConfig | None:
    with st.sidebar:
        st.html(f'''<div class="rm-brand">{logo_html()}</div>
          <div class="rm-sidebar-label">İNCELEMELER</div>''')
        st.button("Yeni analiz", icon=":material/add:", on_click=new_analysis, width="stretch",
                  type="primary" if st.session_state.get("view", "new") == "new" else "secondary")
        history = st.session_state.get("history", {})
        with st.expander(f"Son raporlar · {len(history)}", expanded=True, icon=":material/history:"):
            if not history:
                st.caption("Henüz rapor yok.")
            for report_id, result in reversed(list(history.items())):
                st.button(
                    f"{result.project.name} · {result.score.overall}",
                    key=f"history-{report_id}", on_click=open_report, args=(report_id,), width="stretch",
                    type="primary" if st.session_state.get("active_report") == report_id
                    and st.session_state.get("view") == "report" else "secondary",
                )
            if history:
                st.caption(f"Son {HISTORY_LIMIT} rapor · Bu oturum")
            if history:
                st.button("Oturum geçmişini temizle", on_click=clear_history, icon=":material/delete_outline:", width="stretch")
        st.divider()
        st.html('<div class="rm-sidebar-label">SEÇENEKLER</div>')
        config = _ai_settings()
        st.toggle(
            "Bağımlılık açıklarını tara", value=True, key="osv-enabled",
            help="Sürümü kesin olan paketleri (== ve kilit dosyaları) OSV.dev açık veritabanında arar. "
                 "Yalnızca paket adı ve sürümü gönderilir; kod gönderilmez.",
        )
        st.caption("Ücretsiz OSV.dev veritabanı · yalnızca paket adı ve sürümü")

        st.html('''<div class="rm-sidebar-foot">
          <div class="rm-sidebar-foot-badge"><i></i>GÜVENLİ YEREL MOTOR</div><br>
          Statik analiz yerel çalışır.<br>Kaynak kod asla çalıştırılmaz.</div>''')
        with st.expander("Veri kullanımı", expanded=False, icon=":material/shield:"):
            st.markdown(
                "- Yüklenen dosyalar yalnızca geçici bir klasörde açılır ve analizden hemen sonra **silinir**.\n"
                "- Proje kodu **asla çalıştırılmaz**; yalnızca okunur ve ayrıştırılır (AST).\n"
                "- `.env`, anahtar ve sertifika dosyaları yapay zekâya **gönderilmez**.\n"
                "- Gönderilen kod parçalarındaki parola/anahtar benzeri değerler **maskelenir**.\n"
                "- Bağımlılık taraması açıksa yalnızca paket adları ve sürümleri **OSV.dev**'e gönderilir.\n"
                "- Ollama seçili ve bağımlılık taraması kapalıysa hiçbir veri bilgisayarınızdan çıkmaz.\n"
                "- ZIP Slip ve zip-bomb saldırılarına karşı arşiv yolları ve boyutları denetlenir."
            )
            st.caption("Otomatik ön incelemedir; profesyonel güvenlik denetiminin yerine geçmez.")
    return config
