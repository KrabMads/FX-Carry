"""
fxlens/app.py  — self-contained, no SQLite needed
Fetches live data directly inside Streamlit (cached 6h).
Works on Streamlit Cloud out of the box.
"""

import math
import datetime
import os
import requests
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="fxlens | Carry × Volatility", page_icon="📡",
                   layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Fraunces:ital,wght@0,300;0,600;1,300&display=swap');
  html, body, [class*="css"] { font-family: 'Space Mono', monospace; }
  .main,[data-testid="stAppViewContainer"]{background:#0b0e13;color:#d4dbe8}
  [data-testid="stHeader"]{background:#0b0e13}
  [data-testid="stSidebar"]{background:#12161e}
  h1{font-family:'Fraunces',serif!important;font-weight:300!important;color:#fff!important;letter-spacing:-.5px}
  h2,h3{font-family:'Space Mono',monospace!important;color:#d4dbe8!important;font-size:11px!important;letter-spacing:.12em!important;text-transform:uppercase!important}
  .metric-box{background:#12161e;border:1px solid #1e2535;border-radius:4px;padding:14px 18px;margin-bottom:8px}
  .metric-label{font-size:9px;letter-spacing:.12em;text-transform:uppercase;color:#5a6478;margin-bottom:4px}
  .metric-value{font-size:20px;font-weight:700;color:#fff}
  .metric-sub{font-size:10px;color:#5a6478;margin-top:2px}
  .source-note{background:#12161e;border:1px solid #1e2535;border-left:3px solid #ffd166;padding:12px 16px;border-radius:4px;font-size:10px;color:#5a6478;line-height:1.7;margin-top:20px}
  div[data-testid="stDataFrame"]{border:1px solid #1e2535;border-radius:4px}
</style>
""", unsafe_allow_html=True)

try:
    FRED_API_KEY = st.secrets["FRED_API_KEY"]
except:
    FRED_API_KEY = os.environ.get("FRED_API_KEY", "e1b5a7d1b9c9c52c2a51ceafff0693c5")

GROUP_COLORS = {"Base":"#5a6478","G10":"#00e5b0","Europe":"#74b9ff","EM":"#ff6b6b","GCC":"#ffd166"}

CURRENCIES = [
    ("EUR","Euro","G10","ECBDFR"),
    ("JPY","Japanese Yen","G10","IRSTCI01JPM156N"),
    ("GBP","British Pound","G10","BOEBR"),
    ("CHF","Swiss Franc","G10","SNBPOLFCIR"),
    ("AUD","Australian Dollar","G10","RBATCTR"),
    ("NZD","New Zealand Dollar","G10","RBNZOCR"),
    ("CAD","Canadian Dollar","G10","CAPCBEPCBREPO"),
    ("NOK","Norwegian Krone","Europe","IRSTCI01NOM156N"),
    ("DKK","Danish Krone","Europe","IRSTCI01DKM156N"),
    ("PLN","Polish Zloty","Europe","IRSTCI01PLM156N"),
    ("MXN","Mexican Peso","EM","IRSTCI01MXM156N"),
    ("SAR","Saudi Riyal","GCC",None),
    ("AED","UAE Dirham","GCC",None),
    ("OMR","Omani Rial","GCC",None),
    ("KWD","Kuwaiti Dinar","GCC",None),
    ("QAR","Qatari Riyal","GCC",None),
    ("BHD","Bahraini Dinar","GCC",None),
]

GCC_SPREADS={"SAR":1.00,"AED":-0.10,"OMR":0.50,"KWD":0.00,"QAR":0.60,"BHD":1.00}
GCC_SPOTS={"SAR":3.7500,"AED":3.6725,"OMR":0.3850,"KWD":0.3075,"QAR":3.6400,"BHD":0.3770}

HIST_RATIOS={
    "EUR":{"1Y":-0.33,"3Y":-0.20,"5Y":-0.14,"10Y":-0.07},
    "JPY":{"1Y":-0.43,"3Y":-0.36,"5Y":-0.26,"10Y":-0.19},
    "GBP":{"1Y":0.00,"3Y":-0.06,"5Y":0.00,"10Y":-0.03},
    "CHF":{"1Y":-0.63,"3Y":-0.40,"5Y":-0.49,"10Y":-0.33},
    "AUD":{"1Y":-0.05,"3Y":-0.03,"5Y":-0.02,"10Y":0.13},
    "NZD":{"1Y":-0.03,"3Y":0.05,"5Y":0.06,"10Y":0.16},
    "CAD":{"1Y":-0.06,"3Y":0.00,"5Y":-0.03,"10Y":0.01},
    "NOK":{"1Y":-0.05,"3Y":-0.03,"5Y":-0.08,"10Y":0.00},
    "DKK":{"1Y":-0.86,"3Y":-0.53,"5Y":-0.43,"10Y":-0.25},
    "PLN":{"1Y":0.08,"3Y":0.26,"5Y":0.19,"10Y":0.11},
    "MXN":{"1Y":0.41,"3Y":0.41,"5Y":0.38,"10Y":0.39},
    "SAR":{"1Y":0.72,"3Y":0.52,"5Y":0.38,"10Y":0.25},
    "AED":{"1Y":-0.08,"3Y":-0.05,"5Y":-0.04,"10Y":-0.02},
    "OMR":{"1Y":0.40,"3Y":0.32,"5Y":0.27,"10Y":0.18},
    "KWD":{"1Y":0.05,"3Y":0.08,"5Y":0.12,"10Y":0.20},
    "QAR":{"1Y":0.52,"3Y":0.40,"5Y":0.30,"10Y":0.20},
    "BHD":{"1Y":0.72,"3Y":0.55,"5Y":0.42,"10Y":0.28},
}

FALLBACK={
    "EUR":{"spot":1.0435,"policy_rate":2.15,"vol":6.8},
    "JPY":{"spot":151.80,"policy_rate":0.75,"vol":9.8},
    "GBP":{"spot":1.2595,"policy_rate":3.75,"vol":7.1},
    "CHF":{"spot":0.8992,"policy_rate":0.00,"vol":5.6},
    "AUD":{"spot":0.6352,"policy_rate":3.85,"vol":10.3},
    "NZD":{"spot":0.5748,"policy_rate":2.25,"vol":10.9},
    "CAD":{"spot":1.4280,"policy_rate":2.25,"vol":7.8},
    "NOK":{"spot":11.042,"policy_rate":4.00,"vol":9.2},
    "DKK":{"spot":7.079,"policy_rate":1.75,"vol":3.8},
    "PLN":{"spot":4.068,"policy_rate":4.00,"vol":8.4},
    "MXN":{"spot":20.45,"policy_rate":7.00,"vol":13.8},
    "SAR":{"spot":3.7500,"policy_rate":4.75,"vol":1.2},
    "AED":{"spot":3.6725,"policy_rate":3.65,"vol":0.9},
    "OMR":{"spot":0.3850,"policy_rate":4.25,"vol":1.1},
    "KWD":{"spot":0.3075,"policy_rate":3.75,"vol":1.4},
    "QAR":{"spot":3.6400,"policy_rate":4.35,"vol":1.0},
    "BHD":{"spot":0.3770,"policy_rate":4.75,"vol":1.2},
}

def fetch_fred(series_id):
    r=requests.get("https://api.stlouisfed.org/fred/series/observations",params={
        "series_id":series_id,"api_key":FRED_API_KEY,"file_type":"json",
        "sort_order":"desc","limit":1,"observation_start":"2020-01-01"},timeout=10)
    r.raise_for_status()
    obs=r.json().get("observations",[])
    return float(obs[0]["value"]) if obs and obs[0]["value"]!="." else None

def fetch_spots(codes):
    r=requests.get(f"https://api.exchangerate.host/latest?base=USD&symbols={','.join(codes)}",timeout=10)
    r.raise_for_status()
    return r.json().get("rates",{})

def fetch_history(code,days=35):
    end=datetime.date.today()
    start=end-datetime.timedelta(days=days)
    r=requests.get(f"https://api.exchangerate.host/timeseries?base=USD&symbols={code}&start_date={start}&end_date={end}",timeout=15)
    r.raise_for_status()
    raw=r.json().get("rates",{})
    return {d:v[code] for d,v in sorted(raw.items()) if code in v}

def realised_vol(series):
    prices=list(series.values())
    if len(prices)<5: return None
    rets=[math.log(prices[i]/prices[i-1]) for i in range(1,len(prices))]
    mean=sum(rets)/len(rets)
    var=sum((r-mean)**2 for r in rets)/(len(rets)-1)
    return round(math.sqrt(var)*math.sqrt(252)*100,2)

@st.cache_data(ttl=21600,show_spinner=False)
def load_data():
    rows=[]
    using_fallback=False
    try:
        fed_rate=fetch_fred("FEDFUNDS") or 3.75
    except:
        fed_rate=3.75
        using_fallback=True

    non_gcc=[c[0] for c in CURRENCIES if c[3] is not None]
    try:
        spots=fetch_spots(non_gcc)
    except:
        spots={}
        using_fallback=True

    for code,name,grp,fred_series in CURRENCIES:
        is_gcc=(fred_series is None)
        fb=FALLBACK.get(code,{})

        if is_gcc:
            spot=GCC_SPOTS.get(code)
        else:
            raw=spots.get(code)
            if raw:
                spot=round(1/raw,4) if code in ("EUR","GBP","CHF","AUD","NZD") else raw
            else:
                spot=fb.get("spot"); using_fallback=True

        if is_gcc:
            policy_rate=fed_rate+GCC_SPREADS.get(code,0)
        else:
            try:
                policy_rate=fetch_fred(fred_series) or fb.get("policy_rate",fed_rate)
            except:
                policy_rate=fb.get("policy_rate",fed_rate); using_fallback=True

        carry=round(policy_rate-fed_rate,2)

        if is_gcc:
            vol=fb.get("vol",1.0)
        else:
            try:
                hist=fetch_history(code,days=35)
                vol=realised_vol(hist) or fb.get("vol")
            except:
                vol=fb.get("vol"); using_fallback=True

        ratio=round(carry/vol,3) if vol and vol>0 else None
        h=HIST_RATIOS.get(code,{})
        rows.append({"code":code,"name":name,"grp":grp,"spot":spot,
            "policy_rate":policy_rate,"fed_rate":fed_rate,"carry":carry,
            "vol_1m":vol,"ratio_now":ratio,
            "hist_1y":h.get("1Y"),"hist_3y":h.get("3Y"),
            "hist_5y":h.get("5Y"),"hist_10y":h.get("10Y")})

    return pd.DataFrame(rows),using_fallback,datetime.datetime.utcnow()

# ── HEADER ────────────────────────────────────────────────────────────────────
col_logo,col_meta=st.columns([3,1])
with col_logo:
    st.markdown('<h1>fx<span style="color:#00e5b0;font-style:italic">lens</span></h1>',unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### Controls")
    if st.button("🔄 Refresh Data Now"):
        st.cache_data.clear(); st.rerun()
    st.markdown("---")
    st.markdown("**Group filter**")
    show_groups={g:st.checkbox(g,value=True,key=f"g_{g}") for g in GROUP_COLORS}
    st.markdown("---")
    st.markdown("""<div style="font-size:10px;color:#5a6478;line-height:1.8">
    <b style="color:#d4dbe8">Carry (IRD)</b><br>Foreign rate − US Fed rate<br><br>
    <b style="color:#d4dbe8">1M Vol</b><br>30-day annualised realised vol<br><br>
    <b style="color:#d4dbe8">C/V ratio</b><br>Carry ÷ Vol<br><br>
    <b style="color:#d4dbe8">GCC</b><br>USD-pegged → near-zero vol
    </div>""",unsafe_allow_html=True)

with st.spinner("Loading live FX data..."):
    df,using_fallback,fetch_time=load_data()

with col_meta:
    status="⚠ Fallback data" if using_fallback else "● Live"
    color="#ffd166" if using_fallback else "#00e5b0"
    st.markdown(f"""<div style="text-align:right;padding-top:20px;font-size:10px;color:#5a6478;letter-spacing:.08em">
      <span style="color:{color}">{status}</span><br>{fetch_time.strftime('%Y-%m-%d %H:%M')} UTC<br>vs USD
    </div>""",unsafe_allow_html=True)

st.markdown('<hr style="border-color:#1e2535;margin:4px 0 24px">',unsafe_allow_html=True)

if using_fallback:
    st.warning("⚠ Using fallback data (Feb 2026 snapshot). Click **Refresh Data Now** in the sidebar to retry live fetch.")

active=[g for g,show in show_groups.items() if show]
df=df[df["grp"].isin(active)]
if df.empty:
    st.info("No currencies selected."); st.stop()

mc1,mc2,mc3,mc4=st.columns(4)
best_carry=df.nlargest(1,"carry").iloc[0]
worst_carry=df.nsmallest(1,"carry").iloc[0]
valid_ratio=df[df["ratio_now"].notna()]
best_ratio=valid_ratio.nlargest(1,"ratio_now").iloc[0] if not valid_ratio.empty else None
highest_vol=df.nlargest(1,"vol_1m").iloc[0]

with mc1:
    st.markdown(f"""<div class="metric-box"><div class="metric-label">Highest Carry</div>
      <div class="metric-value" style="color:#00e5b0">{best_carry['code']}</div>
      <div class="metric-sub">+{best_carry['carry']:.2f}% IRD</div></div>""",unsafe_allow_html=True)
with mc2:
    st.markdown(f"""<div class="metric-box"><div class="metric-label">Lowest Carry</div>
      <div class="metric-value" style="color:#ff6b6b">{worst_carry['code']}</div>
      <div class="metric-sub">{worst_carry['carry']:.2f}% IRD</div></div>""",unsafe_allow_html=True)
with mc3:
    if best_ratio is not None:
        st.markdown(f"""<div class="metric-box"><div class="metric-label">Best Carry/Vol</div>
          <div class="metric-value" style="color:#00e5b0">{best_ratio['code']}</div>
          <div class="metric-sub">+{best_ratio['ratio_now']:.2f} ratio</div></div>""",unsafe_allow_html=True)
with mc4:
    st.markdown(f"""<div class="metric-box"><div class="metric-label">Highest Volatility</div>
      <div class="metric-value" style="color:#ffd166">{highest_vol['code']}</div>
      <div class="metric-sub">{highest_vol['vol_1m']:.1f}% vol</div></div>""",unsafe_allow_html=True)

st.markdown("<br>",unsafe_allow_html=True)
st.markdown("### Carry vs Volatility — Scatter")

fig=go.Figure()
for grp,gdf in df.groupby("grp"):
    color=GROUP_COLORS.get(grp,"#888")
    sizes=gdf["ratio_now"].abs().fillna(0.1).clip(0.05,1.5)*16+8
    fig.add_trace(go.Scatter(
        x=gdf["carry"],y=gdf["vol_1m"],mode="markers+text",name=grp,
        text=gdf["code"],textposition="top center",
        textfont=dict(size=10,color=color,family="Space Mono"),
        marker=dict(size=sizes,color=color,opacity=0.75,line=dict(width=1.5,color=color)),
        customdata=gdf[["name","carry","vol_1m","ratio_now","spot","policy_rate"]].values,
        hovertemplate="<b>%{customdata[0]}</b><br>Carry: %{customdata[1]:+.2f}%<br>1M Vol: %{customdata[2]:.1f}%<br>C/V: %{customdata[3]:.3f}<br>Spot: %{customdata[4]:.4f}<br>Policy Rate: %{customdata[5]:.2f}%<extra></extra>"
    ))
fig.add_vline(x=0,line_dash="dash",line_color="#2d3748",line_width=1.5)
fig.update_layout(
    paper_bgcolor="#0b0e13",plot_bgcolor="#12161e",
    font=dict(family="Space Mono",color="#d4dbe8",size=11),
    xaxis=dict(title="Carry — Interest Rate Differential vs USD (%) →",gridcolor="#1e2535",title_font=dict(size=10,color="#5a6478")),
    yaxis=dict(title="1M Realised Volatility (%) →",gridcolor="#1e2535",title_font=dict(size=10,color="#5a6478"),rangemode="tozero"),
    legend=dict(bgcolor="#12161e",bordercolor="#1e2535",borderwidth=1,font=dict(size=10)),
    height=480,margin=dict(l=60,r=30,t=20,b=60),
    hoverlabel=dict(bgcolor="#1a2030",bordercolor="#1e2535",font_family="Space Mono"),
)
st.plotly_chart(fig,use_container_width=True)

st.markdown("<br>",unsafe_allow_html=True)
st.markdown("### Currency Overview")

def fmt_ratio(v):
    if v is None or (isinstance(v,float) and pd.isna(v)): return "—"
    return f"{v:+.2f}"

disp=df.copy()
disp["Spot"]=disp["spot"].apply(lambda v:f"{v:.4f}" if pd.notna(v) else "—")
disp["Policy Rate"]=disp["policy_rate"].apply(lambda v:f"{v:.2f}%")
disp["Fed Rate"]=disp["fed_rate"].apply(lambda v:f"{v:.2f}%")
disp["Carry (IRD)"]=disp["carry"].apply(lambda v:f"{v:+.2f}%")
disp["1M Vol"]=disp["vol_1m"].apply(lambda v:f"{v:.1f}%" if pd.notna(v) else "—")
disp["C/V Now"]=disp["ratio_now"].apply(fmt_ratio)
disp["C/V 1Y"]=disp["hist_1y"].apply(fmt_ratio)
disp["C/V 3Y"]=disp["hist_3y"].apply(fmt_ratio)
disp["C/V 5Y"]=disp["hist_5y"].apply(fmt_ratio)
disp["C/V 10Y"]=disp["hist_10y"].apply(fmt_ratio)
disp["Currency"]=disp["code"]+" — "+disp["name"]

out=disp[["Currency","Spot","Policy Rate","Fed Rate","Carry (IRD)","1M Vol","C/V Now","C/V 1Y","C/V 3Y","C/V 5Y","C/V 10Y"]].reset_index(drop=True)

def color_cell(val):
    try:
        v=float(str(val).replace("%","").replace("+",""))
        if v>0.05: return "color:#00e5b0;font-weight:bold"
        if v<-0.05: return "color:#ff6b6b"
    except: pass
    return ""

styled=(out.style
    .applymap(color_cell,subset=["Carry (IRD)","C/V Now","C/V 1Y","C/V 3Y","C/V 5Y","C/V 10Y"])
    .set_properties(**{"background-color":"#12161e","color":"#d4dbe8","font-family":"Space Mono,monospace","font-size":"11px"})
    .set_table_styles([
        {"selector":"th","props":[("background-color","#0b0e13"),("color","#5a6478"),("font-size","9px"),("letter-spacing","0.1em"),("text-transform","uppercase"),("border-bottom","1px solid #1e2535"),("padding","10px 14px")]},
        {"selector":"td","props":[("padding","9px 14px"),("border-bottom","1px solid #1e2535")]},
    ])
)
st.dataframe(styled,use_container_width=True,hide_index=True,height=580)

st.markdown("""<div class="source-note">
  <b style="color:#ffd166">Sources</b> —
  Policy rates: <b>FRED API</b> (St. Louis Fed) · Spot rates & vol: <b>exchangerate.host</b> ·
  Carry = foreign policy rate − US Fed Funds rate · Vol = 30-day annualised realised volatility ·
  Historical C/V = estimated avg over each lookback · Refreshes every 6 hours
</div>""",unsafe_allow_html=True)
