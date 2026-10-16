"""RepoMentor's workspace: premium developer-grade dark/light design system."""

from __future__ import annotations

NEUTRALS = {
    "card": "color-mix(in srgb, currentColor 3%, transparent)",
    "card-elevated": "color-mix(in srgb, currentColor 4.8%, transparent)",
    "card-hover": "color-mix(in srgb, currentColor 6.5%, transparent)",
    "card-border": "color-mix(in srgb, currentColor 11%, transparent)",
    "card-border-strong": "color-mix(in srgb, currentColor 20%, transparent)",
    "text-secondary": "color-mix(in srgb, currentColor 78%, transparent)",
    "text-muted": "color-mix(in srgb, currentColor 54%, transparent)",
    "track": "color-mix(in srgb, currentColor 10%, transparent)",
    "code-bg": "color-mix(in srgb, currentColor 6%, transparent)",
    "accent": "color-mix(in srgb, currentColor 18%, #dfa83c)",
    "accent-soft": "color-mix(in srgb, #dfa83c 14%, transparent)",
    "accent-border": "color-mix(in srgb, #dfa83c 42%, transparent)",
    "gold": "#e5b84b",
    "magenta": "#c44586",
}
STATUS = {
    "good": "#3fb68b",
    "warning": "#e09f3e",
    "serious": "#e7774a",
    "critical": "#e55365",
    "neutral": "#8b92a6",
}
SEVERITY_STATUS = {
    "critical": "critical",
    "high": "serious",
    "medium": "warning",
    "low": "neutral",
    "info": "neutral",
}
SEVERITY_ICON = {"critical": "✖", "high": "▲", "medium": "●", "low": "↓", "info": "i"}


def css() -> str:
    variables = "\n".join(f"--rm-{name}: {value};" for name, value in {**NEUTRALS, **STATUS}.items())
    return "<style>@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap');\n.stApp {" + variables + "}" + STYLES + "</style>"


STYLES = """
.stApp, .stApp button, .stApp input, .stApp textarea, .stApp select {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}
.stApp code, .stApp pre, .rm-mono {
  font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
}
.stApp {
  font-feature-settings: 'cv02' on, 'cv03' on, 'cv04' on, 'ss01' on;
  -webkit-font-smoothing: antialiased;
  background-image:
    radial-gradient(ellipse 85% 42% at 50% -12%, color-mix(in srgb, #e5b84b 11%, transparent), transparent 72%),
    radial-gradient(ellipse 55% 32% at 88% 4%, color-mix(in srgb, #c44586 6%, transparent), transparent 70%);
  background-attachment: fixed;
}
.block-container {
  padding: 2.2rem 2.8rem 2.4rem;
  max-width: 1400px;
}
[data-testid="stHeader"] { background: transparent; }
[data-testid="stToolbar"] [data-testid="stAppDeployButton"] { display: none; }
h1, h2, h3, h4, h5 { letter-spacing: -.028em; }
[data-testid="stMarkdownContainer"] h4 {
  font-size: 1.04rem;
  font-weight: 650;
  padding: 18px 0 8px;
  letter-spacing: -.02em;
}
[data-testid="stMarkdownContainer"] h5 {
  font-size: .88rem;
  font-weight: 600;
  padding: 12px 0 6px;
  letter-spacing: -.015em;
}
[data-testid="stMarkdownContainer"] p { line-height: 1.65; }

/* Buttons & Inputs */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {
  border-radius: 9px;
  min-height: 41px;
  font-size: .82rem;
  font-weight: 550;
  border: 1px solid var(--rm-card-border);
  background: var(--rm-card);
  transition: all .18s cubic-bezier(0.16, 1, 0.3, 1);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}
.stButton > button p, .stDownloadButton > button p, .stFormSubmitButton > button p {
  font-size: .81rem;
  font-weight: 550;
}
button[kind^="primary"] {
  background: linear-gradient(135deg, #ecc568 0%, #dca338 55%, #cf8f2a 100%) !important;
  color: #191306 !important;
  border: 1px solid rgba(236, 197, 104, 0.65) !important;
  font-weight: 650 !important;
  box-shadow: 0 4px 14px rgba(220, 163, 56, 0.25), inset 0 1px 0 rgba(255, 255, 255, 0.38) !important;
}
button[kind^="primary"]:hover {
  background: linear-gradient(135deg, #f3d27e 0%, #e4b046 55%, #d89b35 100%) !important;
  border-color: #f3d27e !important;
  color: #120d04 !important;
  transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(220, 163, 56, 0.36), inset 0 1px 0 rgba(255, 255, 255, 0.45) !important;
}
button[kind^="primary"] p, button[kind^="primary"] span {
  color: #191306 !important;
  font-weight: 650 !important;
}
.stButton > button:hover, .stDownloadButton > button:hover {
  border-color: var(--rm-accent-border);
  background: var(--rm-card-hover);
  transform: translateY(-1px);
}
[data-testid="stTextInput"] input {
  font-size: .84rem;
}
[data-testid="stTextInputRootElement"], [data-baseweb="select"] > div {
  border-radius: 8px;
  border-color: var(--rm-card-border);
  transition: border-color .15s, box-shadow .15s;
}
[data-testid="stTextInputRootElement"]:focus-within {
  border-color: var(--rm-accent);
  box-shadow: 0 0 0 3px var(--rm-accent-soft);
}
[data-testid="stWidgetLabel"] p {
  font-size: .76rem;
  font-weight: 550;
  color: var(--rm-text-secondary);
}
[data-testid="stCaptionContainer"] p {
  font-size: .73rem;
  color: var(--rm-text-muted);
  line-height: 1.65;
}
[data-testid="stVerticalBlockBorderWrapper"] > div {
  border-radius: 14px;
  border-color: var(--rm-card-border);
}

/* Sidebar */
[data-testid="stSidebar"] {
  border-right: 1px solid var(--rm-card-border);
}
[data-testid="stSidebarUserContent"] { padding: 1.35rem 1.25rem 1.2rem; }
[data-testid="stSidebar"] hr { margin: 1.1rem 0; border-color: var(--rm-card-border); }
[data-testid="stSidebar"] .stButton > button {
  justify-content: flex-start;
  border-color: transparent;
  background: transparent;
  box-shadow: none;
  border-radius: 8px;
  min-height: 38px;
}
[data-testid="stSidebar"] .stButton > button:hover {
  background: var(--rm-code-bg);
  border-color: var(--rm-card-border);
  transform: none;
}
[data-testid="stSidebar"] button[kind^="primary"] {
  background: var(--rm-accent-soft) !important;
  border: 1px solid var(--rm-accent-border) !important;
  border-left: 3px solid var(--rm-accent) !important;
  border-radius: 8px !important;
  box-shadow: none !important;
  transform: none !important;
}
[data-testid="stSidebar"] button[kind^="primary"] p,
[data-testid="stSidebar"] button[kind^="primary"] span {
  color: var(--rm-accent) !important;
  font-weight: 600 !important;
}
[data-testid="stSidebar"] .stButton > button p { text-align: left; font-size: .79rem; }
[data-testid="stSidebar"] [data-testid="stExpander"] details { border: 0; background: transparent; }
[data-testid="stSidebar"] [data-testid="stExpander"] summary { padding-left: 4px; font-size: .78rem; font-weight: 550; }
[data-testid="stSidebar"] [data-testid="stExpanderDetails"] { padding: 4px 0 0; }
.rm-brand {
  width: 100%;
  max-width: 224px;
  aspect-ratio: 3.9;
  overflow: hidden;
  background: #120e17;
  border: 1px solid rgba(229, 184, 75, 0.28);
  border-radius: 10px;
  margin: 2px 0 22px;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.22);
}
.rm-brand-logo {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center 50%;
  transform: scale(1.15);   /* the transparent logo's mark and wordmark span ~73 % of its width */
}
.rm-mobile-brand { display: none; }
.rm-sidebar-label {
  font: 600 .61rem 'JetBrains Mono', ui-monospace, monospace;
  color: var(--rm-text-muted);
  letter-spacing: .13em;
  text-transform: uppercase;
  margin: 18px 0 8px 2px;
}
.rm-sidebar-foot {
  border: 1px solid var(--rm-card-border);
  padding: 13px 14px;
  margin-top: 22px;
  font-size: .71rem;
  line-height: 1.6;
  color: var(--rm-text-secondary);
  background: var(--rm-card);
  border-radius: 10px;
}
.rm-sidebar-foot-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font: 600 .61rem 'JetBrains Mono', ui-monospace, monospace;
  color: var(--rm-good);
  letter-spacing: .04em;
  margin-bottom: 4px;
}
.rm-sidebar-foot-badge i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--rm-good);
  box-shadow: 0 0 8px var(--rm-good);
  display: inline-block;
}

/* Topbar & Hero Section */
.rm-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 14px;
  margin-bottom: 24px;
  border-bottom: 1px solid var(--rm-card-border);
}
.rm-breadcrumb {
  font-size: .76rem;
  font-weight: 500;
  color: var(--rm-text-secondary);
  display: flex;
  align-items: center;
  gap: 8px;
}
.rm-breadcrumb span { color: var(--rm-text-muted); }
.rm-top-meta {
  font: 500 .65rem 'JetBrains Mono', ui-monospace, monospace;
  color: var(--rm-text-secondary);
  background: var(--rm-card-elevated);
  border: 1px solid var(--rm-card-border);
  padding: 4px 11px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  gap: 7px;
}
.rm-top-meta::before {
  content: "";
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--rm-gold);
  box-shadow: 0 0 8px var(--rm-gold);
  display: inline-block;
}
.rm-hero-banner {
  position: relative;
  padding: 26px 28px 24px;
  margin-bottom: 26px;
  border-radius: 16px;
  border: 1px solid var(--rm-card-border-strong);
  background:
    linear-gradient(135deg, color-mix(in srgb, #e5b84b 7%, transparent) 0%, transparent 55%, color-mix(in srgb, #c44586 5%, transparent) 100%),
    var(--rm-card);
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.06);
}
.rm-page-kicker {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font: 600 .62rem 'JetBrains Mono', ui-monospace, monospace;
  color: var(--rm-accent);
  background: var(--rm-accent-soft);
  border: 1px solid var(--rm-accent-border);
  padding: 4px 11px;
  border-radius: 999px;
  letter-spacing: .1em;
  margin-bottom: 14px;
}
.rm-hero-banner h1 {
  font-size: clamp(2.1rem, 3.2vw, 2.85rem);
  line-height: 1.1;
  font-weight: 700;
  letter-spacing: -.045em;
  padding: 0;
  margin: 0 0 10px;
}
.rm-title-period { color: var(--rm-accent); }
.rm-hero-banner p {
  margin: 0;
  max-width: 650px;
  font-size: .9rem;
  line-height: 1.68;
  color: var(--rm-text-secondary);
}
.rm-workflow-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--rm-card-border);
}
.rm-workflow-step {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-radius: 9px;
  background: var(--rm-card-elevated);
  border: 1px solid var(--rm-card-border);
}
.rm-workflow-num {
  font: 700 .64rem 'JetBrains Mono', ui-monospace, monospace;
  color: var(--rm-accent);
  background: var(--rm-accent-soft);
  border: 1px solid var(--rm-accent-border);
  padding: 3px 7px;
  border-radius: 6px;
  flex: none;
}
.rm-workflow-text {
  font-size: .74rem;
  font-weight: 550;
  color: var(--rm-text-secondary);
  line-height: 1.35;
}
.rm-workflow-text small {
  display: block;
  font-size: .65rem;
  font-weight: 400;
  color: var(--rm-text-muted);
}

/* Source Input Card */
.st-key-source-panel {
  padding: 22px 24px 14px;
  background: var(--rm-card);
  border-radius: 14px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.04);
}
.rm-panel-heading {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 8px;
}
.rm-panel-heading h2 {
  font-size: 1.22rem;
  font-weight: 650;
  margin: 2px 0 4px;
  padding: 0;
  letter-spacing: -.03em;
}
.rm-panel-index {
  color: var(--rm-accent);
  font: 600 .62rem 'JetBrains Mono', ui-monospace, monospace;
  letter-spacing: .1em;
}
[data-testid="stTabs"] [role="tablist"] {
  gap: 24px;
  border-color: var(--rm-card-border);
}
[data-testid="stTabs"] [role="tab"] {
  font-size: .82rem;
  font-weight: 550;
  padding: 4px 2px 10px;
}
.st-key-source-panel [data-testid="stTabs"] { gap: 18px; }
.st-key-source-panel [data-testid="stForm"] { padding: 0; }
.rm-source-note {
  display: flex;
  align-items: center;
  gap: 10px;
  border-top: 1px solid var(--rm-card-border);
  padding-top: 12px;
  margin: 12px 0 4px;
}
.rm-note-marker {
  color: var(--rm-good);
  font-size: .82rem;
  background: color-mix(in srgb, var(--rm-good) 14%, transparent);
  border: 1px solid color-mix(in srgb, var(--rm-good) 35%, transparent);
  width: 22px;
  height: 22px;
  border-radius: 6px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
}
.rm-source-note p {
  margin: 0;
  color: var(--rm-text-muted);
  font-size: .71rem;
  line-height: 1.6;
}

/* Example Repositories */
.rm-section-heading {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 15px;
  margin: 28px 0 12px;
}
.rm-section-heading h2 {
  padding: 0;
  margin: 0;
  font-size: .98rem;
  font-weight: 650;
  letter-spacing: -.02em;
}
.rm-section-heading > span {
  font-size: .71rem;
  color: var(--rm-text-muted);
}
.st-key-examples-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
[class*="st-key-demo-"] {
  border: 1px solid var(--rm-card-border);
  border-radius: 12px;
  padding: 15px 18px;
  background: var(--rm-card);
  transition: all .18s cubic-bezier(0.16, 1, 0.3, 1);
}
[class*="st-key-demo-"]:hover {
  border-color: var(--rm-accent-border);
  background: var(--rm-card-elevated);
  transform: translateY(-1px);
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.06);
}
[class*="st-key-demo-"] [data-testid="stHorizontalBlock"] { gap: 14px; }
[class*="st-key-demo-"] .stButton > button {
  border: 1px solid var(--rm-card-border-strong);
  background: var(--rm-card-elevated);
  padding: 0 14px;
  min-height: 36px;
  border-radius: 8px;
  color: var(--rm-text-secondary);
}
[class*="st-key-demo-"] .stButton > button:hover {
  color: var(--rm-accent);
  border-color: var(--rm-accent-border);
  background: var(--rm-accent-soft);
}
.rm-repository-row { display: flex; align-items: flex-start; gap: 14px; }
.rm-repo-symbol {
  flex: none;
  color: var(--rm-accent);
  background: var(--rm-accent-soft);
  border: 1px solid var(--rm-accent-border);
  width: 38px;
  height: 38px;
  border-radius: 9px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 1rem;
  margin-top: 2px;
}
.rm-repository-copy { min-width: 0; flex: 1; }
.rm-repository-title { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; }
.rm-repository-title b {
  font: 600 .86rem 'JetBrains Mono', ui-monospace, monospace;
  letter-spacing: -.02em;
}
.rm-repo-status {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  font-size: .64rem;
  font-weight: 600;
  padding: 2px 9px;
  border-radius: 999px;
}
.rm-repo-status i {
  height: 6px;
  width: 6px;
  display: inline-block;
  border-radius: 50%;
}
.rm-repository-copy p {
  margin: 5px 0 7px;
  font-size: .75rem;
  line-height: 1.55;
  color: var(--rm-text-secondary);
}
.rm-repo-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.rm-repo-chip {
  font: 500 .62rem 'JetBrains Mono', ui-monospace, monospace;
  color: var(--rm-text-muted);
  background: var(--rm-code-bg);
  border: 1px solid var(--rm-card-border);
  padding: 1px 7px;
  border-radius: 5px;
}

/* Analysis Scope Panel */
.rm-scope {
  border: 1px solid var(--rm-card-border);
  border-radius: 14px;
  padding: 22px 22px 18px;
  background: var(--rm-card);
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.04);
}
.rm-scope h2 {
  font-weight: 650;
  font-size: 1.22rem;
  line-height: 1.25;
  letter-spacing: -.03em;
  margin: 4px 0 14px;
  padding: 0;
}
.rm-scope-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 11px 0;
  border-bottom: 1px solid var(--rm-card-border);
}
.rm-scope-row-top {
  display: flex;
  align-items: center;
  gap: 10px;
}
.rm-scope-number {
  color: var(--rm-accent);
  font: 600 .62rem 'JetBrains Mono', ui-monospace, monospace;
  background: var(--rm-accent-soft);
  border: 1px solid var(--rm-accent-border);
  padding: 2px 6px;
  border-radius: 5px;
}
.rm-scope-row b { font-size: .79rem; font-weight: 600; }
.rm-scope-row p {
  margin: 0;
  font-size: .67rem;
  line-height: 1.45;
  color: var(--rm-text-muted);
  padding-left: 34px;
}
.rm-scope-weight {
  margin-left: auto;
  font: 600 .66rem 'JetBrains Mono', ui-monospace, monospace;
  color: var(--rm-accent);
  background: var(--rm-accent-soft);
  padding: 1px 7px;
  border-radius: 999px;
}
.rm-scope-bar {
  height: 4px;
  background: var(--rm-track);
  border-radius: 999px;
  overflow: hidden;
  margin-left: 34px;
}
.rm-scope-bar > span {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, var(--rm-accent), var(--rm-magenta));
  border-radius: 999px;
}
.rm-scope-foot {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 14px 12px;
  margin-top: 14px;
  background: var(--rm-card-elevated);
  border: 1px solid var(--rm-card-border);
  border-radius: 10px;
}
.rm-small-mark {
  font: 700 .8rem 'JetBrains Mono', ui-monospace, monospace;
  color: var(--rm-gold);
  background: #120e17;
  border: 1px solid rgba(229, 184, 75, 0.35);
  padding: 6px 10px;
  border-radius: 7px;
  flex: none;
}
.rm-scope-foot p {
  margin: 0;
  color: var(--rm-text-secondary);
  font-size: .68rem;
  line-height: 1.55;
}

/* Cards & Score Overview (Circular SVG Ring + 2x3 Category Grid) */
.rm-card {
  border: 1px solid var(--rm-card-border);
  border-radius: 12px;
  padding: 18px;
  background: var(--rm-card);
  height: 100%;
}
.rm-label {
  color: var(--rm-text-muted);
  font: 600 .61rem 'JetBrains Mono', ui-monospace, monospace;
  text-transform: uppercase;
  letter-spacing: .09em;
}
.st-key-score-overview {
  background:
    radial-gradient(circle at 12% 50%, color-mix(in srgb, #e5b84b 7%, transparent), transparent 55%),
    var(--rm-card);
  padding: 20px 24px;
  border-radius: 14px;
  box-shadow: 0 6px 26px rgba(0, 0, 0, 0.05);
}
.rm-score-card {
  padding: 6px 4px;
  border: 0;
  border-radius: 0;
  background: transparent;
}
.rm-score-gauge-wrap {
  display: flex;
  align-items: center;
  gap: 20px;
  margin: 14px 0 12px;
}
.rm-gauge-svg {
  width: 112px;
  height: 112px;
  flex: none;
  transform: rotate(-90deg);
}
.rm-gauge-bg {
  fill: none;
  stroke: var(--rm-track);
  stroke-width: 8;
}
.rm-gauge-fill {
  fill: none;
  stroke-width: 8;
  stroke-linecap: round;
  transition: stroke-dashoffset .6s ease;
}
.rm-score-meta-col {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.rm-score-value {
  font-size: 3.6rem;
  letter-spacing: -.06em;
  font-weight: 700;
  line-height: 1;
  font-variant-numeric: tabular-nums;
  margin: 0;
}
.rm-score-value small {
  font: 500 .82rem 'JetBrains Mono', ui-monospace, monospace;
  letter-spacing: 0;
  color: var(--rm-text-muted);
  margin-left: 6px;
}
.rm-score-badges {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 7px;
}
.rm-band {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: .73rem;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 999px;
  background: var(--rm-code-bg);
  border: 1px solid var(--rm-card-border);
}
.rm-grade-pill {
  font: 700 .66rem 'JetBrains Mono', ui-monospace, monospace;
  padding: 3px 8px;
  border-radius: 6px;
  background: var(--rm-accent-soft);
  border: 1px solid var(--rm-accent-border);
  color: var(--rm-accent);
}
.rm-score-scale {
  display: flex;
  gap: 4px;
  margin: 8px 0 12px;
}
.rm-score-scale i {
  flex: 1;
  height: 5px;
  border-radius: 3px;
  background: var(--rm-track);
  overflow: hidden;
}
.rm-score-scale i > b {
  display: block;
  height: 100%;
  background: var(--rm-accent);
  border-radius: 3px;
}
.rm-effort-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 10px 0 6px;
}
.rm-effort-pill {
  font: 500 .63rem 'JetBrains Mono', ui-monospace, monospace;
  color: var(--rm-text-secondary);
  background: var(--rm-card-elevated);
  border: 1px solid var(--rm-card-border);
  padding: 3px 8px;
  border-radius: 6px;
}
.rm-score-note {
  color: var(--rm-text-muted);
  font-size: .67rem;
  margin: 8px 0 0;
  line-height: 1.55;
}

/* 2x3 Category Cards Grid */
.rm-category-card {
  padding: 6px 0 6px 24px;
  border: 0;
  border-left: 1px solid var(--rm-card-border);
  border-radius: 0;
  background: transparent;
}
.rm-cat-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 12px;
}
.rm-cat-box {
  padding: 11px 13px;
  border-radius: 10px;
  border: 1px solid var(--rm-card-border);
  background: var(--rm-card-elevated);
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.rm-cat-box-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.rm-cat-name {
  font-size: .76rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 6px;
}
.rm-cat-name span {
  font: 500 .58rem 'JetBrains Mono', ui-monospace, monospace;
  color: var(--rm-text-muted);
  background: var(--rm-code-bg);
  padding: 1px 5px;
  border-radius: 4px;
}
.rm-cat-val {
  font: 700 .8rem 'JetBrains Mono', ui-monospace, monospace;
  font-variant-numeric: tabular-nums;
}
.rm-meter {
  height: 5px;
  border-radius: 999px;
  background: var(--rm-track);
  overflow: hidden;
}
.rm-meter > div {
  height: 100%;
  background: var(--rm-accent);
  border-radius: 999px;
}

/* Score Factor Breakdown Grid */
.rm-factor-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 8px;
}
.rm-factor-card {
  padding: 14px 16px;
  border-radius: 10px;
  border: 1px solid var(--rm-card-border);
  background: var(--rm-card);
}
.rm-factor-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 8px;
  margin-bottom: 8px;
  border-bottom: 1px solid var(--rm-card-border);
  font-size: .8rem;
  font-weight: 650;
}
.rm-factor-head span {
  font: 600 .68rem 'JetBrains Mono', ui-monospace, monospace;
  color: var(--rm-accent);
}
.rm-factor-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 4px 0;
  font-size: .74rem;
  color: var(--rm-text-secondary);
}
.rm-delta {
  font: 600 .63rem 'JetBrains Mono', ui-monospace, monospace;
  padding: 1px 6px;
  border-radius: 4px;
  min-width: 34px;
  text-align: center;
  flex: none;
}
.rm-delta.pos {
  color: var(--rm-good);
  background: color-mix(in srgb, var(--rm-good) 14%, transparent);
  border: 1px solid color-mix(in srgb, var(--rm-good) 32%, transparent);
}
.rm-delta.neg {
  color: var(--rm-critical);
  background: color-mix(in srgb, var(--rm-critical) 14%, transparent);
  border: 1px solid color-mix(in srgb, var(--rm-critical) 32%, transparent);
}
.rm-delta.zero {
  color: var(--rm-text-muted);
  background: var(--rm-code-bg);
  border: 1px solid var(--rm-card-border);
}

/* Strengths Card */
.rm-strength-list {
  display: flex;
  flex-direction: column;
  gap: 7px;
  margin-top: 6px;
}
.rm-strength-item {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  padding: 9px 12px;
  border-radius: 9px;
  border: 1px solid var(--rm-card-border);
  background: var(--rm-card);
  font-size: .76rem;
  line-height: 1.5;
  color: var(--rm-text-secondary);
}
.rm-strength-icon {
  color: var(--rm-good);
  background: color-mix(in srgb, var(--rm-good) 14%, transparent);
  border: 1px solid color-mix(in srgb, var(--rm-good) 32%, transparent);
  width: 20px;
  height: 20px;
  border-radius: 5px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: .68rem;
  flex: none;
  margin-top: 1px;
}

/* Code Composition & Hygiene Bar (Quality Tab) */
.rm-comp-card {
  padding: 16px 18px;
  border: 1px solid var(--rm-card-border);
  border-radius: 12px;
  background: var(--rm-card);
  margin: 14px 0 18px;
  display: grid;
  grid-template-columns: 1.3fr 1fr;
  gap: 20px;
  align-items: center;
}
.rm-comp-bar {
  display: flex;
  height: 8px;
  border-radius: 999px;
  overflow: hidden;
  background: var(--rm-track);
  margin: 10px 0 8px;
  gap: 2px;
}
.rm-comp-bar > span {
  display: block;
  height: 100%;
}
.rm-comp-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  font-size: .7rem;
  color: var(--rm-text-secondary);
}
.rm-comp-legend span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.rm-hygiene-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}
.rm-hygiene-pill {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 7px 11px;
  border-radius: 8px;
  border: 1px solid var(--rm-card-border);
  background: var(--rm-card-elevated);
  font-size: .72rem;
  color: var(--rm-text-secondary);
}
.rm-hygiene-pill b {
  font: 650 .76rem 'JetBrains Mono', ui-monospace, monospace;
}

/* Stat Grid & Metric Tiles */
.rm-stat-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin: 14px 0 24px;
}
.rm-stat {
  padding: 16px 18px;
  border: 1px solid var(--rm-card-border);
  border-radius: 12px;
  background: var(--rm-card);
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  transition: border-color .16s ease, transform .16s ease;
}
.rm-stat:hover {
  border-color: var(--rm-card-border-strong);
  transform: translateY(-1px);
}
.rm-stat-icon {
  width: 34px;
  height: 34px;
  border-radius: 8px;
  background: var(--rm-accent-soft);
  border: 1px solid var(--rm-accent-border);
  color: var(--rm-accent);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: .95rem;
  flex: none;
}
.rm-stat b {
  display: block;
  font-size: 1.65rem;
  font-weight: 700;
  letter-spacing: -.04em;
  margin: 6px 0 3px;
  font-variant-numeric: tabular-nums;
}
.rm-stat small {
  font-size: .69rem;
  color: var(--rm-text-muted);
}
.rm-tile-value {
  font-size: 1.55rem;
  font-weight: 700;
  letter-spacing: -.04em;
  margin-top: 8px;
  font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere;
}
.rm-tile-note {
  color: var(--rm-text-muted);
  font-size: .68rem;
  margin-top: 6px;
  line-height: 1.55;
}

/* Badges, Severity Summary & Unified Issue Cards */
.rm-badges {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 7px;
  margin-bottom: 8px;
}
.rm-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: .66rem;
  font-weight: 600;
  padding: 2px 9px;
  border-radius: 999px;
  background: var(--rm-code-bg);
  border: 1px solid var(--rm-card-border);
}
.rm-badge .rm-icon { display: none; }
.rm-chip {
  color: var(--rm-text-secondary);
  font: 500 .62rem 'JetBrains Mono', ui-monospace, monospace;
  background: var(--rm-code-bg);
  border: 1px solid var(--rm-card-border);
  padding: 2px 7px;
  border-radius: 5px;
}
.rm-dot {
  height: 6px;
  width: 6px;
  display: inline-block;
  flex: none;
  border-radius: 50%;
}
.rm-sev-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
  margin: 8px 0 18px;
}
.rm-sev-tile {
  padding: 14px 16px;
  border: 1px solid var(--rm-card-border);
  border-top: 3px solid var(--rm-card-border);
  border-radius: 10px;
  background: var(--rm-card);
}
.rm-sev-tile b {
  display: block;
  font-size: 1.5rem;
  font-weight: 700;
  margin-bottom: 4px;
  font-variant-numeric: tabular-nums;
}
.rm-sev-tile span {
  font-size: .7rem;
  font-weight: 550;
  color: var(--rm-text-secondary);
}
[class*="st-key-issue-"] {
  border: 1px solid var(--rm-card-border);
  border-radius: 12px;
  padding: 16px 18px 10px;
  margin-bottom: 12px;
  background: var(--rm-card);
  transition: border-color .16s ease, box-shadow .16s ease;
}
[class*="st-key-issue-"]:hover {
  border-color: var(--rm-card-border-strong);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.05);
}
.rm-issue-header {
  border-left: 3px solid var(--rm-accent);
  padding-left: 12px;
  margin-bottom: 4px;
}
.rm-issue-title {
  font-size: .88rem;
  font-weight: 650;
  margin: 4px 0 5px;
  line-height: 1.4;
}
.rm-issue-loc {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font: 500 .66rem 'JetBrains Mono', ui-monospace, monospace;
  color: var(--rm-text-secondary);
  background: var(--rm-code-bg);
  border: 1px solid var(--rm-card-border);
  padding: 2px 8px;
  border-radius: 5px;
  margin-bottom: 7px;
}
.rm-issue-desc {
  margin: 0;
  font-size: .79rem;
  line-height: 1.6;
  color: var(--rm-text-secondary);
}
[class*="st-key-issue-"] [data-testid="stVerticalBlock"] { gap: .35rem; }
[class*="st-key-issue-"] [data-testid="stExpander"] details {
  border: 0;
  border-top: 1px solid var(--rm-card-border);
  margin-top: 6px;
}
[class*="st-key-issue-"] [data-testid="stExpander"] summary {
  padding: 8px 0 2px;
  font-size: .74rem;
  font-weight: 550;
  color: var(--rm-text-secondary);
}
[class*="st-key-issue-"] [data-testid="stExpanderDetails"] {
  padding-left: 0;
  padding-right: 0;
}

/* Checklists, Facts & Report Heading */
.rm-check {
  display: flex;
  gap: 10px;
  align-items: baseline;
  padding: 8px 0;
  font-size: .79rem;
  border-bottom: 1px solid color-mix(in srgb, currentColor 6%, transparent);
}
.rm-check:last-child { border-bottom: 0; }
.rm-check .ok { color: var(--rm-good); font-weight: 650; }
.rm-check .no { color: var(--rm-critical); font-weight: 650; }
.rm-phase-time, .rm-disclaimer {
  color: var(--rm-text-muted);
  font-size: .71rem;
  font-weight: 450;
}
.rm-phase-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 11px 16px;
  margin: 16px 0 10px;
  background: var(--rm-card-elevated);
  border: 1px solid var(--rm-card-border);
  border-left: 3px solid var(--rm-accent);
  border-radius: 10px;
}
.rm-phase-card h3 {
  margin: 0;
  padding: 0;
  font-size: .98rem;
  font-weight: 650;
}
.rm-facts {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 10px 18px;
  margin: 0;
  font-size: .76rem;
}
.rm-facts dt {
  color: var(--rm-text-muted);
  font-weight: 500;
}
.rm-facts dd {
  font-weight: 550;
}
.rm-facts dt, .rm-facts dd {
  margin: 0;
  padding: 0;
  overflow-wrap: anywhere;
  text-align: left;
}
.rm-facts-card {
  padding: 16px 18px;
  border: 1px solid var(--rm-card-border);
  border-radius: 12px;
  background: var(--rm-card);
}
.rm-report-heading { padding: 2px 0 10px; }
.rm-report-title-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 8px;
}
.rm-report-heading h1 {
  margin: 0;
  padding: 0;
  font-size: 2.15rem;
  font-weight: 700;
  letter-spacing: -.045em;
  overflow-wrap: anywhere;
}
.rm-report-score-pill {
  font: 600 .74rem 'JetBrains Mono', ui-monospace, monospace;
  padding: 4px 11px;
  border-radius: 999px;
  background: var(--rm-accent-soft);
  border: 1px solid var(--rm-accent-border);
  color: var(--rm-accent);
}
.rm-report-meta {
  font-size: .72rem;
  color: var(--rm-text-muted);
  line-height: 1.75;
  display: flex;
  flex-wrap: wrap;
  gap: 6px 14px;
}
.rm-techline {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  margin: 2px 0 12px;
}
.rm-techline span {
  font: 500 .64rem 'JetBrains Mono', ui-monospace, monospace;
  color: var(--rm-text-secondary);
  padding: 3px 9px;
  background: var(--rm-code-bg);
  border: 1px solid var(--rm-card-border);
  border-radius: 6px;
}

/* Segmented Control Navigation */
[data-testid="stButtonGroup"] {
  background: var(--rm-card);
  border: 1px solid var(--rm-card-border);
  border-radius: 11px;
  padding: 5px;
  margin: 8px 0 20px;
  gap: 4px;
}
[data-testid="stButtonGroup"] button {
  border-color: transparent !important;
  background: transparent;
  font-size: .79rem;
  font-weight: 550;
  min-height: 35px;
  border-radius: 8px !important;
  box-shadow: none !important;
}
[data-testid="stButtonGroup"] button[aria-checked="true"] {
  color: var(--rm-accent) !important;
  background: var(--rm-accent-soft) !important;
  border: 1px solid var(--rm-accent-border) !important;
  font-weight: 650;
}

/* Footer */
.rm-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  color: var(--rm-text-muted);
  font-size: .66rem;
  border-top: 1px solid var(--rm-card-border);
  margin-top: 44px;
  padding-top: 18px;
}
.rm-version {
  font: 500 .6rem 'JetBrains Mono', ui-monospace, monospace;
  margin-left: 6px;
  padding: 2px 6px;
  background: var(--rm-code-bg);
  border: 1px solid var(--rm-card-border);
  border-radius: 4px;
}

@media (max-width: 1150px) {
  .block-container { padding-left: 1.7rem; padding-right: 1.7rem; }
  .rm-category-card { padding-left: 16px; }
  .rm-workflow-strip, .rm-comp-card { grid-template-columns: 1fr; }
}
@media (max-width: 640px) {
  .block-container { padding: 3.8rem 1.1rem 1.2rem; }
  .rm-mobile-brand {
    display: block;
    width: 164px;
    aspect-ratio: 3.9;
    background: #120e17;
    border: 1px solid rgba(229, 184, 75, 0.25);
    border-radius: 8px;
    overflow: hidden;
    margin: 0 0 20px;
  }
  .rm-topbar { margin-bottom: 20px; padding-bottom: 12px; }
  .rm-top-meta { display: none; }
  .rm-hero-banner { padding: 18px 16px; }
  .rm-hero-banner h1 { font-size: 1.9rem; }
  .rm-hero-banner p { font-size: .82rem; }
  .st-key-source-panel { padding: 14px 14px 8px; }
  .st-key-source-panel [data-testid="stForm"] [data-testid="stHorizontalBlock"] { gap: 8px; }
  .rm-section-heading > span { font-size: .62rem; }
  .rm-scope { margin-top: 10px; padding: 16px; }
  .rm-scope h2 { font-size: 1.15rem; }
  [class*="st-key-demo-"] [data-testid="stHorizontalBlock"] { flex-wrap: nowrap; }
  [class*="st-key-demo-"] [data-testid="stColumn"]:first-child { flex: 1 1 0%; min-width: 0; }
  [class*="st-key-demo-"] [data-testid="stColumn"]:last-child { flex: 0 0 74px; min-width: 74px; }
  .rm-repo-status { display: none; }
  .rm-repository-row { gap: 10px; }
  .rm-score-gauge-wrap { flex-direction: column; align-items: flex-start; gap: 12px; }
  .rm-category-card { padding: 18px 0 4px; border-left: 0; border-top: 1px solid var(--rm-card-border); }
  .rm-cat-grid, .rm-factor-grid, .rm-hygiene-grid { grid-template-columns: 1fr; }
  .rm-stat-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
  .rm-report-heading h1 { font-size: 1.65rem; }
  .rm-sev-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { transition: none !important; }
}
"""
