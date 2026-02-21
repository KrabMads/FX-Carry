"""
fxlens/app.py
=============
Streamlit dashboard — FX Carry × Volatility

Run locally:
    streamlit run app.py

Deploy free on Streamlit Cloud:
    1. Push this project to a GitHub repo
    2. Go to share.streamlit.io → connect repo → set main file to app.py
    3. Add FRED_API_KEY in the Secrets section (Settings → Secrets)
"""

import sqlite3
import datetime
import os
import subprocess

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ── PAGE CONFIG ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="fxlens | Carry × Volatility",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CUSTOM CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Fraunces:ital,wght@0,300;0,600;1,300&display=swap');

  html, body, [class*="css"] { font-family: 'Space Mono', monospace; }

  .main { background: #0b0e13; }
  [data-testid="stAppViewContainer"] { background: #0b0e13; color: #d4dbe8; }
  [data-testid="stHeader"] { background: #0b0e13; }
  [data-testid="stSidebar"] { background: #12161e; }

  h1 { font-family: 'Fraunces', serif !important; font-weight: 300 !important;
       color: #ffffff !important; letter-spacing: -0.5px; }
  h2, h3 { font-family: 'Space Mono', monospace !important; color: #d4dbe8 !important;
            font-size: 11px !important; letter-spacing: 0.12em !important;
            text-transform: uppercase !important; }

  .metric-box {
    background: #12161e; border: 1px solid #1e2535; border-radius: 4px;
    padding: 14px 18px; margin-bottom: 8px;
  }
  .metric-label { font-size: 9px; letter-spacing: 0.12em; text-transform: uppercase;
                  color: #5a6478; margin-bottom: 4px; }
  .metric-value { font-size: 20px; font-weight: 700; color: #ffffff; }
  .metric-sub   { font-size: 10px; color: #5a6478; margin-top: 2px; }

  .stDataFrame { background: #12161e !important; }
  div[data-testid="stDataFrame"] { border: 1px solid #1e2535; border-radius: 4px; }

  .positive { color: #00e5b0 !important; }
  .negative { color: #ff6b6b !important; }

  .source-note {
    background: #12161e; border: 1px solid #1e2535; border-left: 3px solid #ffd166;
    padding: 12px 16px; border-radius: 4px; font-size: 10px; color: #5a6478;
    line-height: 1.7; margin-top: 20px;
  }
  .stButton button {
    background: #12161e; border: 1px solid #1e2535; color: #d4dbe8;
    font-family: 'Space Mono', monospace; font-size: 10px; letter-spacing: 0.08em;
  }
  .stButton button:hover { border-color: #00e5b0; color: #00e5b0; }
</style>
""", unsafe_allow_html=True)

# ── PATHS ─────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(__file__)
DB_PATH  = os.path.join(BASE_DIR, "data", "fx_data.db")

# ── GROUP COLORS ──────────────────────────────────────────────────────────────
GROUP_COLORS = {
    "Base":   "#5a6478",
    "G10":    "#00e5b0",
    "Europe": "#74b9ff",
    "EM":     "#ff6b6b",
    "GCC":    "#ffd166",
}

# ── DATA LOADING ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)  # cache for 1 hour
def load_latest() -> pd.DataFrame:
    """Load the most recent snapshot from SQLite."""
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()
    con = sqlite3.connect(DB_PATH)
    df = pd.read_sql("""
        SELECT s.*
        FROM fx_snapshots s
        INNER JOIN (
            SELECT code, MAX(fetched_at) AS latest
            FROM fx_snapshots
            GROUP BY code
        ) m ON s.code = m.code AND s.fetched_at = m.latest
        ORDER BY grp, carry DESC
    """, con)
    con.close()
    return df

@st.cache_data(ttl=3600)
def load_fetch_time() -> str:
    if not os.path.exists(DB_PATH):
        return "Never"
    con = sqlite3.connect(DB_PATH)
    row = con.execute("SELECT MAX(fetched_at) FROM fx_snapshots").fetchone()
    con.close()
    if row and row[0]:
        dt = datetime.datetime.fromisoformat(row[0])
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    return "Never"


def fmt_ratio(val):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "—"
    sign = "+" if val > 0 else ""
    return f"{sign}{val:.2f}"

def color_ratio(val):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "color: #5a6478"
    if val > 0.05:
        return "color: #00e5b0; font-weight: 700"
    if val < -0.05:
        return "color: #ff6b6b; font-weight: 700"
    return "color: #d4dbe8"


# ── HEADER ────────────────────────────────────────────────────────────────────
col_logo, col_meta = st.columns([3, 1])
with col_logo:
    st.markdown('<h1>fx<span style="color:#00e5b0;font-style:italic">lens</span></h1>', unsafe_allow_html=True)
with col_meta:
    fetch_time = load_fetch_time()
    st.markdown(f"""
    <div style="text-align:right; padding-top:20px; font-size:10px; color:#5a6478; letter-spacing:0.08em">
      <span style="color:#00e5b0">●</span> LAST UPDATE<br>
      {fetch_time}<br>vs USD
    </div>
    """, unsafe_allow_html=True)

st.markdown('<hr style="border-color:#1e2535; margin: 4px 0 24px">', unsafe_allow_html=True)

# ── REFRESH BUTTON ────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Controls")
    if st.button("🔄 Refresh Data Now"):
        with st.spinner("Fetching live data..."):
            result = subprocess.run(
                ["python3", os.path.join(BASE_DIR, "fetch_data.py")],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                st.success("Data updated!")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error(f"Fetch failed:\n{result.stderr}")

    st.markdown("---")
    st.markdown("**Group filter**")
    show_groups = {}
    for g, col in GROUP_COLORS.items():
        show_groups[g] = st.checkbox(g, value=True, key=f"grp_{g}")

    st.markdown("---")
    st.markdown("**About**")
    st.markdown("""
    <div style="font-size:10px;color:#5a6478;line-height:1.8">
    <b style="color:#d4dbe8">Carry (IRD)</b><br>
    Foreign policy rate minus US Fed Funds rate.<br><br>
    <b style="color:#d4dbe8">1M Vol</b><br>
    30-day annualised realised volatility from daily spot.<br><br>
    <b style="color:#d4dbe8">C/V ratio</b><br>
    Carry ÷ Volatility. Higher = better risk-adjusted carry.<br><br>
    <b style="color:#d4dbe8">GCC currencies</b><br>
    USD-pegged → structural near-zero vol.
    </div>
    """, unsafe_allow_html=True)

# ── LOAD DATA ─────────────────────────────────────────────────────────────────
df = load_latest()

if df.empty:
    st.warning("""
    **No data yet.** Run the fetcher first:
    ```bash
    python fetch_data.py
    ```
    Or click **Refresh Data Now** in the sidebar (requires FRED_API_KEY to be set).
    """)
    st.stop()

# Apply group filter
active_groups = [g for g, show in show_groups.items() if show]
df = df[df["grp"].isin(active_groups)]

# ── TOP METRICS ───────────────────────────────────────────────────────────────
mc1, mc2, mc3, mc4 = st.columns(4)

best_carry = df.nlargest(1, "carry").iloc[0]
worst_carry = df.nsmallest(1, "carry").iloc[0]
best_ratio = df[df["ratio_now"].notna()].nlargest(1, "ratio_now").iloc[0]
highest_vol = df.nlargest(1, "vol_1m").iloc[0]

with mc1:
    st.markdown(f"""
    <div class="metric-box">
      <div class="metric-label">Highest Carry</div>
      <div class="metric-value" style="color:#00e5b0">{best_carry['code']}</div>
      <div class="metric-sub">+{best_carry['carry']:.2f}% IRD</div>
    </div>""", unsafe_allow_html=True)

with mc2:
    st.markdown(f"""
    <div class="metric-box">
      <div class="metric-label">Lowest Carry</div>
      <div class="metric-value" style="color:#ff6b6b">{worst_carry['code']}</div>
      <div class="metric-sub">{worst_carry['carry']:.2f}% IRD</div>
    </div>""", unsafe_allow_html=True)

with mc3:
    st.markdown(f"""
    <div class="metric-box">
      <div class="metric-label">Best Carry/Vol</div>
      <div class="metric-value" style="color:#00e5b0">{best_ratio['code']}</div>
      <div class="metric-sub">+{best_ratio['ratio_now']:.2f} ratio</div>
    </div>""", unsafe_allow_html=True)

with mc4:
    st.markdown(f"""
    <div class="metric-box">
      <div class="metric-label">Highest Volatility</div>
      <div class="metric-value" style="color:#ffd166">{highest_vol['code']}</div>
      <div class="metric-sub">{highest_vol['vol_1m']:.1f}% 1M vol</div>
    </div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── SCATTER CHART ─────────────────────────────────────────────────────────────
st.markdown("### Carry vs Volatility — Scatter")

fig = go.Figure()

for grp, grp_df in df.groupby("grp"):
    color = GROUP_COLORS.get(grp, "#888")
    fig.add_trace(go.Scatter(
        x=grp_df["carry"],
        y=grp_df["vol_1m"],
        mode="markers+text",
        name=grp,
        text=grp_df["code"],
        textposition="top center",
        textfont=dict(size=10, color=color, family="Space Mono"),
        marker=dict(
            size=grp_df["ratio_now"].abs().fillna(0).clip(0.01, 1.5) * 16 + 8,
            color=color,
            opacity=0.75,
            line=dict(width=1.5, color=color),
        ),
        customdata=grp_df[["name", "carry", "vol_1m", "ratio_now", "spot", "policy_rate"]].values,
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Carry: %{customdata[1]:+.2f}%<br>"
            "1M Vol: %{customdata[2]:.1f}%<br>"
            "C/V: %{customdata[3]:.3f}<br>"
            "Spot: %{customdata[4]:.4f}<br>"
            "Policy Rate: %{customdata[5]:.2f}%"
            "<extra></extra>"
        )
    ))

# Zero line
fig.add_vline(x=0, line_dash="dash", line_color="#2d3748", line_width=1.5)

fig.update_layout(
    paper_bgcolor="#0b0e13",
    plot_bgcolor="#12161e",
    font=dict(family="Space Mono", color="#d4dbe8", size=11),
    xaxis=dict(
        title="Carry — Interest Rate Differential vs USD (%) →",
        gridcolor="#1e2535", zerolinecolor="#1e2535",
        title_font=dict(size=10, color="#5a6478"),
    ),
    yaxis=dict(
        title="1M Realised Volatility (%) →",
        gridcolor="#1e2535", zerolinecolor="#1e2535",
        title_font=dict(size=10, color="#5a6478"),
        rangemode="tozero",
    ),
    legend=dict(
        bgcolor="#12161e", bordercolor="#1e2535", borderwidth=1,
        font=dict(size=10),
    ),
    height=480,
    margin=dict(l=60, r=30, t=20, b=60),
    hoverlabel=dict(bgcolor="#1a2030", bordercolor="#1e2535", font_family="Space Mono"),
)

st.plotly_chart(fig, use_container_width=True)

# ── TABLE ─────────────────────────────────────────────────────────────────────
st.markdown("<br>", unsafe_allow_html=True)
st.markdown("### Currency Overview")

# Build display dataframe
display = df[[
    "code", "name", "grp", "spot", "policy_rate", "fed_rate",
    "carry", "vol_1m", "ratio_now",
    "hist_1y", "hist_3y", "hist_5y", "hist_10y"
]].copy()

display.columns = [
    "Code", "Name", "Group", "Spot", "Policy Rate", "Fed Rate",
    "Carry (IRD)", "1M Vol", "C/V Now",
    "C/V 1Y", "C/V 3Y", "C/V 5Y", "C/V 10Y"
]

# Format columns
def fmt_pct(v):
    if pd.isna(v): return "—"
    return f"{v:+.2f}%" if v != 0 else "0.00%"

def fmt_spot(v):
    if pd.isna(v): return "—"
    return f"{v:.4f}"

# Style function for the whole dataframe
def style_table(df):
    styled = df.style

    def color_carry(val):
        try:
            v = float(str(val).replace("%","").replace("+",""))
            if v > 0.1: return "color: #00e5b0; font-weight: bold"
            if v < -0.1: return "color: #ff6b6b; font-weight: bold"
        except: pass
        return "color: #d4dbe8"

    def color_cv(val):
        try:
            v = float(str(val).replace("+",""))
            if v > 0.05: return "color: #00e5b0; font-weight: bold"
            if v < -0.05: return "color: #ff6b6b"
        except: pass
        return "color: #5a6478"

    carry_cols = ["Carry (IRD)"]
    cv_cols = ["C/V Now", "C/V 1Y", "C/V 3Y", "C/V 5Y", "C/V 10Y"]

    for col in carry_cols:
        styled = styled.applymap(color_carry, subset=[col])
    for col in cv_cols:
        styled = styled.applymap(color_cv, subset=[col])

    styled = styled.set_properties(**{
        "background-color": "#12161e",
        "color": "#d4dbe8",
        "border-color": "#1e2535",
        "font-family": "Space Mono, monospace",
        "font-size": "11px",
    })
    styled = styled.set_table_styles([
        {"selector": "th", "props": [
            ("background-color", "#0b0e13"),
            ("color", "#5a6478"),
            ("font-size", "9px"),
            ("letter-spacing", "0.1em"),
            ("text-transform", "uppercase"),
            ("border-bottom", "1px solid #1e2535"),
            ("padding", "10px 14px"),
        ]},
        {"selector": "td", "props": [("padding", "9px 14px"), ("border-bottom", "1px solid #1e2535")]},
        {"selector": "tr:hover td", "props": [("background-color", "#1a2030")]},
    ])
    return styled

# Format for display
disp_fmt = display.copy()
disp_fmt["Spot"]        = disp_fmt["Spot"].apply(fmt_spot)
disp_fmt["Policy Rate"] = disp_fmt["Policy Rate"].apply(lambda v: f"{v:.2f}%" if pd.notna(v) else "—")
disp_fmt["Fed Rate"]    = disp_fmt["Fed Rate"].apply(lambda v: f"{v:.2f}%" if pd.notna(v) else "—")
disp_fmt["Carry (IRD)"] = disp_fmt["Carry (IRD)"].apply(fmt_pct)
disp_fmt["1M Vol"]      = disp_fmt["1M Vol"].apply(lambda v: f"{v:.1f}%" if pd.notna(v) else "—")
for col in ["C/V Now", "C/V 1Y", "C/V 3Y", "C/V 5Y", "C/V 10Y"]:
    disp_fmt[col] = disp_fmt[col].apply(fmt_ratio)

st.dataframe(
    style_table(disp_fmt),
    use_container_width=True,
    hide_index=True,
    height=600,
)

# ── DATA SOURCE NOTE ──────────────────────────────────────────────────────────
st.markdown("""
<div class="source-note">
  <b style="color:#ffd166">Sources</b> —
  Policy rates: <b>FRED API</b> (St. Louis Fed, stlouisfed.org) ·
  Spot rates & history: <b>exchangerate.host</b> ·
  Carry = foreign policy rate − US Fed Funds rate ·
  Vol = 30-day annualised realised volatility from daily spot prices ·
  Historical C/V = estimated avg carry/vol over each lookback window ·
  GCC currencies are USD-pegged (near-zero structural vol)
</div>
""", unsafe_allow_html=True)
