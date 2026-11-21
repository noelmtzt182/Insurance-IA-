"""Estilo visual: minimalista, fondo blanco, inspirado en plataformas analíticas."""
from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

INK = "#0B0F14"
INK_2 = "#4A5260"
MUTED = "#8A919C"
LINE = "#E4E7EB"
SURFACE = "#FFFFFF"
SURFACE_2 = "#F6F7F9"
ACCENT = "#2A78D6"

# Paleta categórica validada (orden fijo, nunca ciclada)
SERIES = ["#2A78D6", "#EB6834", "#1BAF7A", "#EDA100", "#E87BA4", "#008300", "#6250D6", "#E34948"]
# Secuencial de un solo tono (azul) claro → oscuro
SEQ_BLUE = ["#CFE0F6", "#9DC0EC", "#6A9FE2", "#2A78D6", "#1D5BA8", "#123F78"]

PRODUCT_COLORS = {"Seguro de vida": SERIES[0], "Gastos médicos mayores": SERIES[1]}
PRIORITY_COLORS = {"Alta prioridad": SEQ_BLUE[4], "Media": SEQ_BLUE[2], "Exploratorio": SEQ_BLUE[0]}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500&display=swap');
html, body, [class*="css"], .stMarkdown, .stText, button, input, textarea, select {
  font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif !important;
}
.stApp { background: #FFFFFF; }
.block-container { padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1400px; }
[data-testid="stSidebar"] { background: #F6F7F9; border-right: 1px solid #E4E7EB; }
[data-testid="stSidebar"] .block-container { padding-top: 1rem; }
h1, h2, h3 { color: #0B0F14; letter-spacing: -0.02em; font-weight: 650; }
h1 { font-size: 1.65rem !important; }
h2 { font-size: 1.25rem !important; }
h3 { font-size: 1.05rem !important; }
.ila-eyebrow { font-size: .72rem; letter-spacing: .12em; text-transform: uppercase; color: #8A919C; font-weight: 600; margin-bottom: .15rem; }
.ila-sub { color: #4A5260; font-size: .92rem; margin-top: -.4rem; margin-bottom: 1.2rem; }
.ila-brand { display:flex; align-items:center; gap:.55rem; padding:.3rem 0 1rem 0; border-bottom:1px solid #E4E7EB; margin-bottom: .8rem;}
.ila-brand-mark { width:28px; height:28px; border-radius:6px; background:#0B0F14; color:#fff; display:flex; align-items:center; justify-content:center; font-weight:700; font-size:.8rem; }
.ila-brand-name { font-weight:650; color:#0B0F14; font-size:.98rem; line-height:1.1; }
.ila-brand-tag { color:#8A919C; font-size:.72rem; }
.ila-kpi { border:1px solid #E4E7EB; border-radius:8px; padding:.75rem .85rem .7rem .85rem; background:#FFFFFF; height:100%; min-width:0; }
.ila-kpi-label { font-size:.68rem; letter-spacing:.06em; text-transform:uppercase; color:#8A919C; font-weight:600;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.ila-kpi-value { font-family:'JetBrains Mono', ui-monospace, monospace; font-size:clamp(.95rem, 1.45vw, 1.5rem); color:#0B0F14;
  font-weight:500; margin-top:.2rem; line-height:1.25; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.ila-kpi-help { font-size:.72rem; color:#4A5260; margin-top:.2rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.ila-stages { display:flex; flex-wrap:wrap; gap:.4rem; margin:.2rem 0 1rem 0; }
.ila-stage { border:1px solid #E4E7EB; border-radius:999px; padding:.2rem .7rem; font-size:.8rem; color:#4A5260; background:#FFFFFF; }
.ila-stage b { color:#0B0F14; font-family:'JetBrains Mono', ui-monospace, monospace; font-weight:500; margin-left:.25rem; }
.ila-pill { display:inline-block; padding:.1rem .55rem; border-radius:999px; font-size:.75rem; font-weight:600; border:1px solid #E4E7EB; color:#0B0F14; background:#F6F7F9;}
.ila-banner { border:1px solid #F2D9A6; background:#FFF8E8; color:#5C4300; border-radius:8px; padding:.55rem .85rem; font-size:.85rem; margin-bottom:1rem; }
.ila-card { border:1px solid #E4E7EB; border-radius:8px; padding:1rem 1.1rem; background:#FFFFFF; }
div[data-testid="stMetric"] { border:1px solid #E4E7EB; border-radius:8px; padding:.6rem .9rem; }
.stTabs [data-baseweb="tab-list"] { gap: 1.2rem; border-bottom: 1px solid #E4E7EB; }
.stTabs [data-baseweb="tab"] { padding-left: 0; padding-right: 0; }
div[data-testid="stForm"] { border:1px solid #E4E7EB; border-radius:10px; }
</style>
"""

HIDE_SIDEBAR_CSS = """
<style>
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="collapsedControl"] { display:none !important; }
.block-container { max-width: 760px; }
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
        margin=dict(l=10, r=10, t=56, b=10),
        title=dict(font=dict(size=14, color=INK), x=0, xanchor="left"),
        xaxis=dict(showgrid=False, linecolor=LINE, tickcolor=LINE, zeroline=False),
        yaxis=dict(gridcolor="#EEF0F3", zeroline=False, linecolor=LINE),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, title_text=""),
        hoverlabel=dict(bgcolor="#FFFFFF", bordercolor=LINE, font=dict(color=INK, family="Inter")),
        bargap=0.25,
    )
    pio.templates["ila"] = tpl
    pio.templates.default = "ila"


_register_plotly_template()
