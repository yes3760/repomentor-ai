import pytest

from repomentor.ai import llm_analyzer
from repomentor.ai.llm_analyzer import is_cv_style, is_duplicate, is_sendable, select_snippets
from repomentor.ai.providers import LLMConfig, LLMError, _is_free_chat_model
from repomentor.ai.response_parser import ParseError, extract_json, normalise_response
from tests.conftest import EXAMPLES, analyze


def test_extract_json_handles_fences_and_chatter():
    assert extract_json('Tabii!\n```json\n{"summary": "ok",}\n```') == {"summary": "ok"}


def test_extract_json_repairs_truncated_output():
    assert extract_json('{"summary": "ok", "strengths": ["a", "b"')["strengths"] == ["a", "b"]


def test_extract_json_rejects_garbage():
    with pytest.raises(ParseError):
        extract_json("Üzgünüm, yardımcı olamam.")


def test_normalise_maps_turkish_values_and_drops_hallucinated_paths():
    data = normalise_response({
        "issues": [
            {"title": "Hata yönetimi zayıf", "severity": "Yüksek", "category": "kalite", "file": "app/main.py",
             "explanation": "x", "recommendation": "y", "estimated_minutes": "45 dakika"},
            {"title": "Uydurma", "severity": "low", "category": "quality", "file": "olmayan/dosya.py",
             "explanation": "x", "recommendation": "y", "estimated_minutes": 10},
            {"title": "Eksik öneri"},
        ],
        "strengths": "- bir\n- iki",
    }, known_paths={"app/main.py"})
    first, second = data["issues"]
    assert (first.severity, first.category, first.file, first.effort_minutes) == ("high", "quality", "app/main.py", 45)
    assert second.file is None
    assert data["strengths"] == ["bir", "iki"]


def test_duplicate_and_style_gates():
    assert is_duplicate("score() çok karmaşık (karmaşıklık 12)", ["`score()` çok karmaşık (karmaşıklık 12)"])
    assert not is_duplicate("Hata mesajları kullanıcıya gösterilmiyor", ["README çok kısa"])
    assert is_cv_style(["FastAPI ile REST API geliştirdim.", "pytest ile testler yazdım.", "Docker ile paketledim."])
    assert not is_cv_style(["Proje, Streamlit kullanarak veri analizi geliştirmektedir.", "Docker kullanmaktadır."])


def test_secrets_and_env_files_are_never_sent():
    assert not is_sendable(".env")
    assert not is_sendable("config/.env.production")
    assert not is_sendable("keys/server.pem")
    assert is_sendable("app/main.py")


def test_prompt_is_masked(problematic_result):
    from repomentor.analyzer.context import AnalysisContext
    from repomentor.analyzer.file_tree import scan_project

    project = scan_project(EXAMPLES / "problematic_project")
    r = problematic_result
    ctx = AnalysisContext(project, r.project, r.documentation, r.tests, r.security, r.quality, r.issues)
    prompt = llm_analyzer.build_prompt(ctx, r.score, 12_000)
    assert "Ankara2024!" not in prompt
    assert "a1b2c3d4e5f6g7h8i9j0-demo-not-real" not in prompt
    assert len(prompt) < 16_000
    snippets = select_snippets(project, r.project, r.quality, 4000)
    assert snippets and all(path.endswith(".py") for path, _ in snippets)


def test_openrouter_only_free_models():
    assert _is_free_chat_model("openrouter", "meta-llama/llama-3.3-70b-instruct:free")
    assert not _is_free_chat_model("openrouter", "openai/gpt-4o")
    assert not _is_free_chat_model("groq", "whisper-large-v3")


FAKE_RESPONSE = """{
  "summary": "Görev yönetimi için temiz bir FastAPI servisi.",
  "architecture_review": "Katmanlar ayrılmış.",
  "readability_review": "İsimler anlaşılır.",
  "strengths": ["Parametreli SQL", "Parametreli SQL kullanımı", "Katmanlı yapı"],
  "issues": [
    {"title": "Hata loglanmıyor", "severity": "medium", "category": "quality", "file": "app/main.py",
     "explanation": "Hatalar iz bırakmıyor.", "recommendation": "logging ekleyin.", "estimated_minutes": 20},
    {"title": "README dosyası yok", "severity": "high", "category": "documentation", "file": "README.md",
     "explanation": "x", "recommendation": "y", "estimated_minutes": 30}
  ],
  "readme_suggestions": ["API örneği ekleyin"],
  "next_steps": ["Loglama ekle", "Loglama ekle"],
  "cv_bullets": ["FastAPI ve SQLite ile REST API geliştirdim.", "pytest ile 10 test yazdım."],
  "linkedin_short": "FastAPI ile görev API'si geliştirdim.",
  "linkedin_post": "Yeni projem..."
}"""


def test_pipeline_with_fake_llm(monkeypatch):
    monkeypatch.setattr(llm_analyzer, "chat_json", lambda *a, **k: FAKE_RESPONSE)
    config = LLMConfig(provider="ollama", model="fake")
    result = analyze(EXAMPLES / "clean_project", llm=config)
    assert result.ai.ok
    assert result.ai.summary.startswith("Görev yönetimi")
    assert [i.title for i in result.ai.extra_issues] == ["Hata loglanmıyor"]
    assert result.ai.extra_issues[0].source == "ai"
    assert result.ai.next_steps == ["Loglama ekle"]
    assert result.ai.strengths == ["Parametreli SQL", "Katmanlı yapı"]
    assert result.career.source == "ai"
    assert all(i.source != "ai" for i in result.issues), "AI issues must not affect the score"


def test_pipeline_survives_llm_failure(monkeypatch):
    def boom(*args, **kwargs):
        raise LLMError("ücretsiz katman sınırı")

    monkeypatch.setattr(llm_analyzer, "chat_json", boom)
    result = analyze(EXAMPLES / "medium_project", llm=LLMConfig(provider="groq", model="x", api_key="k"))
    assert result.ai.error == "ücretsiz katman sınırı"
    assert result.career.source == "rule"
    assert result.score.overall > 0
    assert any("ücretsiz katman sınırı" in w for w in result.warnings)


def test_unsupported_claims_are_removed(problematic_result):
    from repomentor.analyzer.context import AnalysisContext
    from repomentor.analyzer.file_tree import scan_project

    r = problematic_result
    ctx = AnalysisContext(scan_project(EXAMPLES / "problematic_project"), r.project, r.documentation, r.tests, r.security, r.quality, r.issues)
    data = {
        "cv_bullets": [
            "Python ve Flask kullanarak REST API geliştirdim.",
            "Gizli bilgileri .env dosyasında güvenli şekilde sakladım.",
            "pytest ile birim testleri yazdım.",
            "SQLite ile veri katmanını kurdum.",
        ],
        "linkedin_short": "Flask ile not sistemi geliştirdim.",
        "linkedin_post": "Flask ile not sistemi geliştirdim.",
    }
    career = llm_analyzer._career(data, ctx, r.score, r.career)
    text = " ".join(career.cv_bullets)
    assert "REST API geliştirdim" in text and "SQLite" in text
    assert ".env" not in text and "pytest" not in text, "claims contradicting the analysis must be dropped"
    assert career.linkedin_post == r.career.linkedin_post, "too-short AI post falls back to the template"
    assert not llm_analyzer.is_supported("Kod okunabilir ve temiz.", ctx, r.score)
