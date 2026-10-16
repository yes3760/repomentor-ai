"""Bounded, per-browser-session reports. No disk persistence or shared report cache."""

from __future__ import annotations

from uuid import uuid4

import streamlit as st

from repomentor.models.analysis_result import AnalysisResult

HISTORY_LIMIT = 5


def remember_result(result: AnalysisResult) -> None:
    history = st.session_state.setdefault("history", {})
    report_id = uuid4().hex[:12]
    history[report_id] = result
    while len(history) > HISTORY_LIMIT:
        expired = next(iter(history))
        del history[expired]
        st.session_state.get("completed_steps", {}).pop(expired, None)
        for key in list(st.session_state):
            if key.startswith((f"findings-{expired}-", f"files-{expired}-", f"roadmap-{expired}-")):
                del st.session_state[key]
    open_report(report_id)


def open_report(report_id: str) -> None:
    st.session_state["active_report"] = report_id
    st.session_state["result"] = st.session_state["history"][report_id]
    st.session_state["view"] = "report"


def new_analysis() -> None:
    st.session_state["view"] = "new"


def clear_history() -> None:
    for key in list(st.session_state):
        if key.startswith(("roadmap-", "findings-", "compare-", "files-", "report-section-")):
            del st.session_state[key]
    for key in ("history", "result", "active_report", "completed_steps"):
        st.session_state.pop(key, None)
    new_analysis()


def report_key() -> str:
    return st.session_state.get("active_report", "current")


def save_step(report_id: str, step_id: str, widget_key: str) -> None:
    completed = st.session_state.setdefault("completed_steps", {}).setdefault(report_id, set())
    if st.session_state[widget_key]:
        completed.add(step_id)
    else:
        completed.discard(step_id)
