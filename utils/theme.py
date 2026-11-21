"""Estilo visual: fondo blanco, azul marino institucional y acentos naranja.

El CSS fuerza el tema claro aunque falte `.streamlit/config.toml` (por ejemplo, si
la carpeta oculta no se subió a GitHub) o el navegador esté en modo oscuro.
"""
from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# --- Tokens de color -------------------------------------------------------
NAVY = "#0B2A5B"        # azul marino institucional (menú, títulos)
NAVY_2 = "#143C7A"      # azul marino claro (hover / activo)
ORANGE = "#E35205"      # acento y botones principales
ORANGE_DARK = "#C24400"  # hover de botones
ORANGE_SOFT = "#FFF1E8"  # fondos suaves de acento
INK = "#1A2433"         # texto principal
INK_2 = "#4B5565"       # texto secundario
MUTED = "#6B7585"       # texto auxiliar (contraste ≥ 4.5:1 sobre blanco)
LINE = "#E1E6EE"        # bordes
SURFACE = "#FFFFFF"
SURFACE_2 = "#F4F6FA"
ACCENT = ORANGE

# Paleta categórica validada (daltonismo y contraste) — orden fijo, nunca ciclada
SERIES = ["#1F4E9C", "#E35205", "#1BAF7A", "#EDA100", "#E87BA4", "#008300", "#6250D6", "#E34948"]
# Secuencial de un solo tono (azul marino), claro → oscuro, validada
SEQ_BLUE = ["#97ADD6", "#6E8FC6", "#466FB0", "#1F4E9C", "#0B2A5B"]

PRODUCT_COLORS = {"Seguro de vida": SERIES[0], "Gastos médicos mayores": SERIES[1]}
PRIORITY_COLORS = {"Alta prioridad": SEQ_BLUE[4], "Media": SEQ_BLUE[2], "Exploratorio": SEQ_BLUE[0]}

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500&display=swap');
:root {{
  --ila-navy:{NAVY}; --ila-navy-2:{NAVY_2}; --ila-orange:{ORANGE}; --ila-orange-dark:{ORANGE_DARK};
  --ila-orange-soft:{ORANGE_SOFT}; --ila-ink:{INK}; --ila-ink-2:{INK_2}; --ila-muted:{MUTED};
  --ila-line:{LINE}; --ila-surface:{SURFACE}; --ila-surface-2:{SURFACE_2};
  color-scheme: light;
}}

/* ---------- Tema claro forzado (independiente de config.toml / modo oscuro) ---------- */
[data-testid="stHeader"] {{ background: transparent !important; }}
html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"],
[data-testid="stBottom"] > div {{ background: var(--ila-surface) !important; color: var(--ila-ink) !important; }}
html, body, .stApp, .stMarkdown, button, input, textarea, select {{
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif !important;
}}
[data-testid="stMain"] p, [data-testid="stMain"] li, [data-testid="stMain"] span, [data-testid="stMain"] label,
[data-testid="stMain"] [data-testid="stMarkdownContainer"], [data-testid="stMain"] [data-testid="stWidgetLabel"] p,
[data-testid="stMain"] [data-testid="stCaptionContainer"], [data-testid="stMain"] small {{ color: inherit; }}
[data-testid="stMain"] {{ color: var(--ila-ink) !important; }}
[data-testid="stMain"] [data-testid="stCaptionContainer"], [data-testid="stMain"] [data-testid="stCaptionContainer"] p {{
  color: var(--ila-muted) !important; }}
h1, h2, h3, h4, h5, h6, [data-testid="stMain"] h1 span, [data-testid="stMain"] h2 span, [data-testid="stMain"] h3 span {{
  color: var(--ila-navy) !important; letter-spacing: -0.02em; font-weight: 650; }}
h1 {{ font-size: 1.65rem !important; }}
h2 {{ font-size: 1.25rem !important; }}
h3 {{ font-size: 1.05rem !important; }}
a, a:visited {{ color: var(--ila-orange-dark); }}

/* Campos de formulario */
[data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="textarea"], [data-baseweb="select"] > div,
[data-testid="stDateInput"] [data-baseweb="input"], [data-testid="stNumberInput"] [data-baseweb="input"] {{
  background: var(--ila-surface) !important; border-color: #C9D2DF !important; }}
[data-baseweb="input"] input, [data-baseweb="base-input"] input, textarea, [data-baseweb="select"] div,
[data-baseweb="select"] input {{ color: var(--ila-ink) !important; -webkit-text-fill-color: var(--ila-ink) !important;
  background: transparent !important; }}
input::placeholder, textarea::placeholder {{ color: #8A93A3 !important; -webkit-text-fill-color: #8A93A3 !important; }}
[data-testid="stNumberInput"] button {{ background: var(--ila-surface-2) !important; color: var(--ila-ink) !important; }}
/* Streamlit ≥ 1.5x (react-aria): contenedores de campos y textos de widgets */
[data-testid="stMain"] [role="group"], [data-testid="stMain"] [data-testid$="RootElement"],
[data-testid="stMain"] [data-testid="stDateInputField"], [data-testid="stMain"] [data-testid="stTextArea"] textarea {{
  background: var(--ila-surface) !important; border-color: #C9D2DF !important; }}
[data-testid="stMain"] input, [data-testid="stMain"] textarea, [data-testid="stMain"] [role="combobox"] {{
  color: var(--ila-ink) !important; -webkit-text-fill-color: var(--ila-ink) !important; }}
[data-testid="stMain"] [data-testid="stDateInputFieldsScroller"] span,
[data-testid="stMain"] [data-testid="stRadioOption"] label, [data-testid="stMain"] [data-testid="stRadioOption"] span,
[data-testid="stMain"] [data-testid="stCheckbox"] label, [data-testid="stMain"] [data-testid="stCheckbox"] span,
[data-testid="stMain"] [data-testid="stWidgetLabel"], [data-testid="stMain"] [data-testid="stWidgetLabel"] p {{
  color: var(--ila-ink) !important; }}
[data-testid="stMain"] [data-testid="stTab"], [data-testid="stMain"] [data-testid="stTab"] p {{ color: var(--ila-ink-2) !important; }}
[data-testid="stMain"] [data-testid="stTab"][aria-selected="true"], [data-testid="stMain"] [data-testid="stTab"][aria-selected="true"] p {{
  color: var(--ila-navy) !important; font-weight: 600; }}
[role="listbox"], [role="option"], [role="dialog"], [data-testid="stSelectboxVirtualDropdown"] {{
  background: var(--ila-surface) !important; color: var(--ila-ink) !important; }}
[role="option"]:hover, [role="option"][data-focused="true"] {{ background: var(--ila-orange-soft) !important; }}
[data-testid="stMain"] [data-testid="stTabs"] [data-baseweb="tab-highlight"],
[data-testid="stMain"] [role="tablist"] [data-testid="stTabHighlight"] {{ background: var(--ila-orange) !important; }}
[data-testid="stMain"] input[type="checkbox"], [data-testid="stMain"] input[type="radio"] {{ accent-color: var(--ila-orange); }}
[data-baseweb="popover"], [data-baseweb="popover"] ul, [data-baseweb="menu"], [role="listbox"] {{
  background: var(--ila-surface) !important; color: var(--ila-ink) !important; }}
[data-baseweb="popover"] li, [role="option"] {{ color: var(--ila-ink) !important; }}
[data-baseweb="popover"] li:hover, [role="option"][aria-selected="true"] {{ background: var(--ila-orange-soft) !important; }}
[data-baseweb="tag"] {{ background: var(--ila-orange-soft) !important; color: var(--ila-orange-dark) !important; }}
[data-baseweb="tag"] span {{ color: var(--ila-orange-dark) !important; }}

/* Botones */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button, .stLinkButton > a {{
  border-radius: 8px !important; font-weight: 600 !important; border: 1px solid #C9D2DF !important;
  background: var(--ila-surface) !important; color: var(--ila-navy) !important; }}
.stButton > button:hover, .stDownloadButton > button:hover, .stFormSubmitButton > button:hover, .stLinkButton > a:hover {{
  border-color: var(--ila-orange) !important; color: var(--ila-orange-dark) !important; }}
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primaryFormSubmit"],
.stDownloadButton > button[kind="primary"], .stLinkButton > a[kind="primary"],
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"],
[data-testid="stBaseLinkButton-primary"] {{
  background: var(--ila-orange) !important; border-color: var(--ila-orange) !important; color: #FFFFFF !important; }}
[data-testid="stBaseButton-primary"] p, [data-testid="stBaseButton-primaryFormSubmit"] p,
[data-testid="stBaseLinkButton-primary"] p,
.stButton > button[kind="primary"] p, .stFormSubmitButton > button[kind="primaryFormSubmit"] p,
.stLinkButton > a[kind="primary"] p {{ color: #FFFFFF !important; }}
[data-testid="stBaseButton-primary"]:hover, [data-testid="stBaseButton-primaryFormSubmit"]:hover,
.stButton > button[kind="primary"]:hover, .stFormSubmitButton > button[kind="primaryFormSubmit"]:hover {{
  background: var(--ila-orange-dark) !important; border-color: var(--ila-orange-dark) !important; color: #FFFFFF !important; }}

/* Pestañas, expanders, alertas, tablas */
.stTabs [data-baseweb="tab-list"] {{ gap: 1.2rem; border-bottom: 1px solid var(--ila-line); }}
.stTabs [data-baseweb="tab"] {{ padding-left: 0; padding-right: 0; color: var(--ila-ink-2) !important; background: transparent !important; }}
.stTabs [aria-selected="true"], .stTabs [aria-selected="true"] p {{ color: var(--ila-navy) !important; font-weight: 600; }}
.stTabs [data-baseweb="tab-highlight"] {{ background: var(--ila-orange) !important; }}
[data-testid="stExpander"] details, [data-testid="stExpander"] summary {{ background: var(--ila-surface) !important;
  color: var(--ila-ink) !important; border-color: var(--ila-line) !important; }}
div[data-testid="stForm"] {{ border: 1px solid var(--ila-line); border-radius: 10px; background: var(--ila-surface); }}
[data-testid="stDataFrame"], [data-testid="stTable"] {{ border: 1px solid var(--ila-line); border-radius: 8px; }}
[data-testid="stChatMessage"] {{ background: var(--ila-surface-2) !important; color: var(--ila-ink) !important; }}
div[data-testid="stMetric"] {{ border: 1px solid var(--ila-line); border-radius: 8px; padding: .6rem .9rem; background: var(--ila-surface); }}
[data-testid="stMetricValue"], [data-testid="stMetricLabel"] p {{ color: var(--ila-ink) !important; }}

/* ---------- Menú lateral azul marino ---------- */
[data-testid="stSidebar"], [data-testid="stSidebar"] > div:first-child, [data-testid="stSidebarContent"],
[data-testid="stSidebarHeader"], [data-testid="stSidebarUserContent"], [data-testid="stSidebarNav"],
[data-testid="stSidebarNavItems"] {{ background: var(--ila-navy) !important; }}
[data-testid="stSidebar"] {{ border-right: 0; }}
[data-testid="stSidebar"] *, [data-testid="stSidebar"] p, [data-testid="stSidebar"] span, [data-testid="stSidebar"] label {{
  color: #E8EEF8 !important; }}
[data-testid="stSidebarNav"] [data-testid="stNavSectionHeader"], [data-testid="stSidebarNav"] header,
[data-testid="stSidebar"] [data-testid="stNavSectionHeader"] span {{
  color: #9FB3D6 !important; text-transform: uppercase; font-size: .7rem !important; letter-spacing: .1em; }}
[data-testid="stSidebarNav"] a {{ border-radius: 6px; border-left: 3px solid transparent; }}
[data-testid="stSidebarNav"] a:hover {{ background: var(--ila-navy-2) !important; }}
[data-testid="stSidebarNav"] a[aria-current="page"] {{ background: var(--ila-navy-2) !important;
  border-left-color: var(--ila-orange) !important; }}
[data-testid="stSidebarNav"] a[aria-current="page"] span {{ color: #FFFFFF !important; font-weight: 600; }}
[data-testid="stSidebar"] [data-baseweb="select"] > div {{ background: #FFFFFF !important; }}
[data-testid="stSidebar"] [data-baseweb="select"] div, [data-testid="stSidebar"] [data-baseweb="select"] span {{
  color: var(--ila-ink) !important; }}
[data-testid="stSidebar"] .stButton > button {{ background: transparent !important; color: #FFFFFF !important;
  border-color: #3D5C8F !important; }}
[data-testid="stSidebar"] .stButton > button p {{ color: #FFFFFF !important; }}
[data-testid="stSidebar"] hr {{ border-color: #23457E !important; }}

/* ---------- Componentes propios ---------- */
/* Espacio para la barra superior (en Streamlit Cloud es más alta que en local) */
.block-container, [data-testid="stMainBlockContainer"] {{ padding-top: 5rem !important; padding-bottom: 3rem;
  max-width: 1400px; }}
.ila-eyebrow {{ font-size: .72rem; letter-spacing: .12em; text-transform: uppercase; color: var(--ila-orange-dark) !important;
  font-weight: 700; margin-bottom: .15rem; }}
.ila-sub {{ color: var(--ila-ink-2) !important; font-size: .92rem; margin-top: -.4rem; margin-bottom: 1.2rem; }}
.ila-brand {{ display:flex; align-items:center; gap:.55rem; padding:.3rem 0 1rem 0; border-bottom:1px solid #23457E; margin-bottom:.8rem; }}
.ila-brand-mark {{ width:28px; height:28px; border-radius:6px; background:var(--ila-orange); color:#FFFFFF !important;
  display:flex; align-items:center; justify-content:center; font-weight:700; font-size:.8rem; }}
.ila-brand-name {{ font-weight:650; color:#FFFFFF !important; font-size:.98rem; line-height:1.1; }}
.ila-brand-tag {{ color:#9FB3D6 !important; font-size:.72rem; }}
.ila-login .ila-brand {{ border-bottom-color: var(--ila-line); }}
.ila-login .ila-brand-name {{ color: var(--ila-navy) !important; }}
.ila-login .ila-brand-tag {{ color: var(--ila-muted) !important; }}
.ila-kpi {{ border:1px solid var(--ila-line); border-top:3px solid var(--ila-orange); border-radius:8px;
  padding:.7rem .85rem .7rem .85rem; background:var(--ila-surface); height:100%; min-width:0; }}
.ila-kpi-label {{ font-size:.68rem; letter-spacing:.06em; text-transform:uppercase; color:var(--ila-muted) !important;
  font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.ila-kpi-value {{ font-family:'JetBrains Mono', ui-monospace, monospace; font-size:clamp(.95rem, 1.45vw, 1.5rem);
  color:var(--ila-navy) !important; font-weight:500; margin-top:.2rem; line-height:1.25; white-space:nowrap;
  overflow:hidden; text-overflow:ellipsis; }}
.ila-kpi-help {{ font-size:.72rem; color:var(--ila-ink-2) !important; margin-top:.2rem; white-space:nowrap; overflow:hidden;
  text-overflow:ellipsis; }}
.ila-stages {{ display:flex; flex-wrap:wrap; gap:.4rem; margin:.2rem 0 1rem 0; }}
.ila-stage {{ border:1px solid var(--ila-line); border-radius:999px; padding:.2rem .7rem; font-size:.8rem;
  color:var(--ila-ink-2) !important; background:var(--ila-surface); }}
.ila-stage b {{ color:var(--ila-navy) !important; font-family:'JetBrains Mono', ui-monospace, monospace; font-weight:500; margin-left:.25rem; }}
.ila-pill {{ display:inline-block; padding:.1rem .55rem; border-radius:999px; font-size:.75rem; font-weight:600;
  border:1px solid var(--ila-line); color:var(--ila-navy) !important; background:var(--ila-surface-2); }}
.ila-banner {{ border:1px solid #F5C9A8; background:var(--ila-orange-soft); color:#7A2E00 !important; border-radius:8px;
  padding:.55rem .85rem; font-size:.85rem; margin-bottom:1rem; }}
.ila-banner b, .ila-banner i {{ color:#7A2E00 !important; }}
.ila-card {{ border:1px solid var(--ila-line); border-top:3px solid var(--ila-orange); border-radius:8px;
  padding:1rem 1.1rem; background:var(--ila-surface); }}
.ila-card b {{ color: var(--ila-navy) !important; }}
.ila-hero {{ background: var(--ila-navy); border-radius: 12px; padding: 1.6rem 1.6rem 1.4rem 1.6rem; margin-bottom: 1.2rem; }}
.ila-hero .ila-hero-eyebrow {{ color: #FFB27D !important; font-size:.72rem; letter-spacing:.12em; text-transform:uppercase; font-weight:700; }}
.ila-hero h1, .ila-hero .ila-hero-title {{ color: #FFFFFF !important; font-size: 1.7rem; font-weight: 700; line-height: 1.2;
  margin: .3rem 0 .4rem 0; letter-spacing: -0.02em; }}
.ila-hero .ila-hero-sub {{ color: #D6E0F0 !important; font-size: .98rem; }}
.ila-hero .ila-hero-accent {{ color: #FFB27D !important; }}
</style>
"""

HIDE_SIDEBAR_CSS = """
<style>
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="collapsedControl"] { display:none !important; }
.block-container { max-width: 780px; }
</style>
"""


def inject_css(public: bool = False) -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    if public:
        st.markdown(HIDE_SIDEBAR_CSS, unsafe_allow_html=True)


def _register_plotly_template() -> None:
    tpl = go.layout.Template()
    tpl.layout = go.Layout(
        font=dict(family="Inter, system-ui, sans-serif", size=12, color=INK_2),
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        colorway=SERIES,
        margin=dict(l=10, r=10, t=84, b=10),
        title=dict(font=dict(size=14, color=NAVY), x=0, xanchor="left", y=0.98, yref="container", yanchor="top"),
        xaxis=dict(showgrid=False, linecolor=LINE, tickcolor=LINE, zeroline=False, tickfont=dict(color=INK_2),
                   automargin=True),
        yaxis=dict(gridcolor="#EEF1F6", zeroline=False, linecolor=LINE, tickfont=dict(color=INK_2)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title_text="",
                    font=dict(color=INK_2)),
        hoverlabel=dict(bgcolor="#FFFFFF", bordercolor=LINE, font=dict(color=INK, family="Inter")),
        bargap=0.25,
    )
    pio.templates["ila"] = tpl
    pio.templates.default = "ila"


_register_plotly_template()
