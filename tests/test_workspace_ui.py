"""Stateful user journeys: reports, navigation, isolated tasks and cleanup."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app.py"


def workspace():
    return AppTest.from_file(str(APP), default_timeout=20).run()


def button(at, label):
    return next(b for b in at.button if b.label == label)


def section(at, label):
    at.segmented_control[0].set_value(label).run()
    assert not at.exception


def test_analysis_is_opt_in_and_invalid_input_keeps_workspace_usable():
    at = workspace()
    assert not at.toggle[0].value
    button(at, "Projeyi analiz et").click().run()
    assert at.error and not at.exception
    at.text_input[0].set_value("https://example.com/not-github").run()
    button(at, "Projeyi analiz et").click().run()
    assert "GitHub" in at.error[0].value
    assert not at.exception


def test_task_completion_survives_navigation_and_is_report_specific():
    at = workspace()
    at.button(key="demo-problematic_project-run").click().run()
    first_id = at.session_state["active_report"]
    section(at, "Yol haritası")
    at.checkbox[0].check().run()
    section(at, "Portföy")
    section(at, "Yol haritası")
    assert at.checkbox[0].value
    button(at, "Yeni analiz").click().run()
    at.button(key="demo-problematic_project-run").click().run()
    second_id = at.session_state["active_report"]
    assert first_id != second_id
    section(at, "Yol haritası")
    assert not at.checkbox[0].value
    at.button(key=f"history-{first_id}").click().run()
    section(at, "Yol haritası")
    assert at.checkbox[0].value
    section(at, "Karşılaştır")
    assert at.metric[0].delta == "+0 puan"


def test_findings_search_reset_and_technical_views():
    at = workspace()
    at.button(key="demo-problematic_project-run").click().run()
    section(at, "Bulgular")
    prefix = f"findings-{at.session_state['active_report']}"
    at.selectbox(key=f"{prefix}-page").set_value(2).run()
    at.text_input(key=f"{prefix}-query").set_value(" ").run()
    assert at.session_state[f"{prefix}-page"] == 1
    assert not at.exception
    at.text_input(key=f"{prefix}-query").set_value("nonexistent-finding-zz").run()
    assert at.info and "eşleşen bulgu yok" in at.info[0].value
    section(at, "Teknik analiz")
    assert not at.exception


def test_history_is_bounded_and_can_be_cleared():
    at = workspace()
    for _ in range(6):
        at.button(key="demo-clean_project-run").click().run()
        button(at, "Yeni analiz").click().run()
    assert len(at.session_state["history"]) == 5
    button(at, "Oturum geçmişini temizle").click().run()
    assert not at.exception
    assert "history" not in at.session_state
    assert "result" not in at.session_state
    assert not at.segmented_control


def test_engine_sections_and_fix_patch_are_shown():
    at = workspace()
    at.button(key="demo-problematic_project-run").click().run()
    section(at, "Yol haritası")
    texts = [m.value for m in at.markdown]
    assert "##### Otomatik düzeltme yaması" in texts
    assert any(e.label.startswith("utils.py") for e in at.expander)
    section(at, "Teknik analiz")
    texts = [m.value for m in at.markdown]
    assert {"##### Kullanılmayan kod", "##### Kontrol akışı", "##### Testlerin ulaştığı kod (statik)"} <= set(texts)
    assert not at.exception


def test_data_science_section_for_ml_projects():
    at = workspace()
    at.button(key="demo-ml_project-run").click().run()
    section(at, "Teknik analiz")
    assert "##### Veri bilimi kontrolleri" in [m.value for m in at.markdown]
    assert any("veri sızıntısı" in e.value for e in at.error)
    assert not at.exception


def test_notebook_demo_runs():
    at = workspace()
    at.button(key="demo-notebook_project-run").click().run()
    assert not at.exception
    section(at, "Teknik analiz")
    assert "##### Veri bilimi kontrolleri" in [m.value for m in at.markdown]


def test_visual_sections():
    at = workspace()
    at.button(key="demo-problematic_project-run").click().run()
    assert "##### Kod haritası" in [m.value for m in at.markdown]
    section(at, "Teknik analiz")
    assert "##### Saldırı yolu" in [m.value for m in at.markdown]
    section(at, "Portföy")
    assert "##### README rozeti" in [m.value for m in at.markdown]
    assert any("img.shields.io/badge/RepoMentor_AI-" in c.value for c in at.code)
    assert not at.exception


def test_attack_path_shows_the_verified_fix():
    at = workspace()
    at.button(key="demo-problematic_project-run").click().run()
    section(at, "Teknik analiz")
    flows = at.session_state["history"][at.session_state["active_report"]].security.taint_flows
    sql = next(i for i, f in enumerate(flows) if f.kind == "sql")
    at.selectbox(key=f"flow-path-{at.session_state['active_report']}").set_value(sql).run()
    assert any("doğrulanmış bir düzeltme" in s.value for s in at.success)
    assert any('cur.execute("SELECT * FROM ogrenciler WHERE ad = ?", (ad,))' in c.value for c in at.code)
    assert not at.exception
