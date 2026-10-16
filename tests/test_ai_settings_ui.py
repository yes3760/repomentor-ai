"""Sidebar AI settings: provider choice, live Ollama state, API keys. Never touches the network."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from repomentor.ui import sidebar

APP = Path(__file__).resolve().parents[1] / "app.py"


class FakeProviders:
    """Stands in for Ollama and the cloud model lists; tests flip its state between reruns."""

    def __init__(self):
        self.ollama_up = True
        self.ollama_models = ["qwen2.5-coder:7b", "llama3.2:3b"]
        self.cloud_models = {"groq": ["llama-3.3-70b-versatile"]}

    def available(self, *args, **kwargs):
        return self.ollama_up

    def models(self, provider, api_key=None, *args, **kwargs):
        if provider == "ollama":
            return list(self.ollama_models) if self.ollama_up else []
        return list(self.cloud_models.get(provider, [])) if api_key else []


@pytest.fixture
def fake(monkeypatch):
    providers = FakeProviders()
    monkeypatch.setattr(sidebar, "ollama_available", providers.available)
    monkeypatch.setattr(sidebar, "list_models", providers.models)
    for env in ("GROQ_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(env, raising=False)
    sidebar._remote_models.clear()
    return providers


def ai_on():
    at = AppTest.from_file(str(APP), default_timeout=20).run()
    at.toggle(key="ai-enabled").set_value(True).run()
    assert not at.exception
    return at


def texts(at) -> str:
    return " ".join(e.value for kind in (at.caption, at.error, at.warning, at.info) for e in kind)


def test_provider_list_is_short_and_has_no_redundant_off_option(fake):
    at = ai_on()
    provider = at.selectbox(key="ai-provider")
    assert provider.options == ["Ollama (yerel)", "Groq", "Google Gemini", "OpenRouter"]
    assert provider.value == "ollama", "a running Ollama is the default"


def test_ollama_changes_show_up_without_waiting_for_a_cache(fake):
    fake.ollama_up = False
    at = ai_on()
    assert "Ollama çalışmıyor" in texts(at)
    fake.ollama_up, fake.ollama_models = True, []
    at.button(key="ollama-retry").click().run()
    assert "yüklü model yok" in texts(at)
    fake.ollama_models = ["llama3.2:3b"]
    at.button(key="ollama-retry").click().run()
    assert at.selectbox(key="ollama-model").options == ["llama3.2:3b"]


def test_pull_advice_only_when_the_model_is_small(fake):
    at = ai_on()
    assert at.selectbox(key="ollama-model").value == "qwen2.5-coder:7b"
    assert "ollama pull" not in texts(at), "the recommended model is installed: no download advice"
    fake.ollama_models = ["llama3.2:3b"]
    at.run()
    assert "ollama pull qwen2.5-coder:7b" in texts(at)


def test_cloud_provider_asks_for_a_key_then_lists_models(fake):
    at = ai_on()
    at.selectbox(key="ai-provider").set_value("groq").run()
    key = at.text_input(key="api-key-groq")
    assert key.label == "API anahtarı" and "Anahtar girilene kadar" in texts(at)
    key.set_value("gsk-test").run()
    assert at.selectbox(key="model-groq").options == ["llama-3.3-70b-versatile"]
    assert not at.exception


def test_wrong_key_falls_back_to_a_typed_model_name(fake):
    fake.cloud_models = {}
    at = ai_on()
    at.selectbox(key="ai-provider").set_value("groq").run()
    at.text_input(key="api-key-groq").set_value("wrong").run()
    assert "Model listesi alınamadı" in texts(at)
    assert at.text_input(key="model-name-groq").value == "llama-3.3-70b-versatile"
