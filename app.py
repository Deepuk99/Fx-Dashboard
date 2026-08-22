import csv
import io
from datetime import datetime

import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import requests
import streamlit as st

# =========================================================
# CONFIG
# =========================================================
CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vS17geJblGtzfcq5AYKaaRakdMtFpuHKaE_H-vg1BndiU1qV02hkH5BZiPA1qpbZExCH_nh5X9jUi_W/pub?gid=438761626&single=true&output=csv"

st.set_page_config(
    page_title="FX Performance Terminal",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =========================================================
# DARK TRADING-TERMINAL THEME
# =========================================================
st.markdown("""
<style>
    .stApp { background-color: #0a0e14; color: #d1d5db; }
    section[data-testid="stSidebar"] { background-color: #10141c; border-right: 1px solid #1f2733; }
    h1, h2, h3 { color: #e5e7eb !important; font-family: 'Courier New', monospace; }
    .stat-card {
        background: linear-gradient(145deg, #12161f, #0d1017);
        border: 1px solid #1f2733;
        border-radius: 10px;
        padding: 16px 18px;
        text-align: left;
    }
    .stat-label { color: #8b93a3; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px; }
    .stat-value { font-size: 26px; font-weight: 700; font-family: 'Courier New', monospace; }
    .green { color: #22c55e; }
    .red { color: #ef4444; }
    .neutral { color: #e5e7eb; }
    .ticker-wrap {
        width: 100%; overflow: hidden; background: #0d1017;
        border-top: 1px solid #1f2733; border-bottom: 1px solid #1f2733;
        padding: 8px 0; margin-bottom: 18px;
    }
    .ticker-move {
        display: inline-block; white-space: nowrap;
        animation: ticker 40s linear infinite;
        font-family: 'Courier New', monospace; font-size: 14px;
    }
    @keyframes ticker { 0% { transform: translateX(0); } 100% { transform: translateX(-50%); } }
    .ticker-item { display: inline-block; padding: 0 24px; }
    div[data-testid="stDataFrame"] { border: 1px solid #1f2733; border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

# =========================================================
# DATA LOADING & PARSING
# =========================================================
EXPECTED_COLS = ['Blank', '#', 'Mth', 'P', 'Date', 'WK', 'W/L', 'Pair', 'Action',
                  'Pip', 'Session', 'Lot', 'Swap', 'Charges', 'P&L', 'Day Total',
                  'Actl Pft %', 'TP', 'SL', 'RR', 'R Multiple', 'Risk %', 'Exit',
                  'Actual Hit', 'Why', 'Setup', 'Model', 'EN/T', 'Avd']


def clean_numeric(series):
    return pd.to_numeric(
        series.astype(str)
        .str.replace('%', '', regex=False)
        .str.replace(',', '', regex=False)
        .str.replace('₹', '', regex=False)
        .str.strip()
        .replace({'-': None, '': None, 'nan': None, '#DIV/0!': None, '#N/A': None, '#REF!': None}),
        errors='coerce'
    )


@st.cache_data(ttl=300, show_spinner=False)
def load_data(url: str) -> pd.DataFrame:
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    text = resp.content.decode('utf-8', errors='replace')
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)

    header_idx = None
    for i, row in enumerate(rows):
        if len(row) > 4 and row[1].strip() == '#' and row[4].strip() == 'Date':
            header_idx = i
            break
    if header_idx is None:
        raise ValueError("Could not locate the trade-journal header row in the sheet.")

    data_rows = []
    for row in rows[header_idx + 1:]:
        if len(row) < 29:
            row = row + [''] * (29 - len(row))
        data_rows.append(row[0:29])

    df = pd.DataFrame(data_rows, columns=EXPECTED_COLS)
    df = df.drop(columns=['Blank'])

    # Keep only real trade rows: must have a dd/mm/yyyy date and a Won/Loss result
    df['Date'] = pd.to_datetime(df['Date'], format='%d/%m/%Y', errors='coerce')
    df = df[df['Date'].notna()]
    df = df[df['W/L'].isin(['Won', 'Loss'])]

    # Numeric conversions
    for col in ['Pip', 'Lot', 'Swap', 'Charges', 'P&L', 'Day Total', 'Actl Pft %',
                'TP', 'SL', 'RR', 'R Multiple']:
        df[col] = clean_numeric(df[col])

    df['Win'] = (df['W/L'] == 'Won').astype(int)
    df['Setup'] = df['Setup'].fillna('Unknown').replace('', 'Unknown')
    df['Model'] = df['Model'].fillna('N/A').replace('', 'N/A')
    df['Session'] = df['Session'].fillna('Unknown').replace('', 'Unknown')
    df['Pair'] = df['Pair'].fillna('Unknown').replace('', 'Unknown')
    df['Action'] = df['Action'].fillna('Unknown').replace('', 'Unknown')
    df['Month'] = df['Date'].dt.to_period('M').dt.to_timestamp()

    df = df.sort_values('Date').reset_index(drop=True)
    df['Trade No'] = range(1, len(df) + 1)
    df['Cum P&L'] = df['P&L'].fillna(0).cumsum()
    running_max = df['Cum P&L'].cummax()
    df['Drawdown'] = df['Cum P&L'] - running_max

    return df


try:
    df_raw = load_data(CSV_URL)
except Exception as e:
    st.error(f"Could not load trade data from the Google Sheet: {e}")
    st.stop()

if df_raw.empty:
    st.warning("No trade rows were found. Check the sheet's publish-to-web link and format.")
    st.stop()

# =========================================================
# SIDEBAR FILTERS
# =========================================================
st.sidebar.markdown("## ⚙️ Filters")

min_date, max_date = df_raw['Date'].min().date(), df_raw['Date'].max().date()
date_range = st.sidebar.date_input(
    "Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date
)
if isinstance(date_range, tuple) and len(date_range) == 2:
    start_date, end_date = date_range
else:
    start_date, end_date = min_date, max_date

pairs = sorted(df_raw['Pair'].unique())
sel_pairs = st.sidebar.multiselect("Currency Pair", pairs, default=pairs)

models = sorted(df_raw['Model'].unique())
sel_models = st.sidebar.multiselect("Setup / Model", models, default=models)

setups = sorted(df_raw['Setup'].unique())
sel_setups = st.sidebar.multiselect("Trade Type", setups, default=setups)

sessions = sorted(df_raw['Session'].unique())
sel_sessions = st.sidebar.multiselect("Session", sessions, default=sessions)

actions = sorted(df_raw['Action'].unique())
sel_actions = st.sidebar.multiselect("Action", actions, default=actions)

wl_options = ['Won', 'Loss']
sel_wl = st.sidebar.multiselect("Result", wl_options, default=wl_options)

st.sidebar.markdown("---")
st.sidebar.caption(f"Data cached for 5 min · refreshes automatically\n\nLast row in sheet: {max_date}")
if st.sidebar.button("🔄 Force refresh now"):
    st.cache_data.clear()
    st.rerun()

mask = (
    (df_raw['Date'].dt.date >= start_date) &
    (df_raw['Date'].dt.date <= end_date) &
    (df_raw['Pair'].isin(sel_pairs)) &
    (df_raw['Model'].isin(sel_models)) &
    (df_raw['Setup'].isin(sel_setups)) &
    (df_raw['Session'].isin(sel_sessions)) &
    (df_raw['Action'].isin(sel_actions)) &
    (df_raw['W/L'].isin(sel_wl))
)
df = df_raw[mask].copy()

if df.empty:
    st.warning("No trades match the current filters. Adjust filters in the sidebar.")
    st.stop()

# Recompute equity curve / drawdown on the FILTERED set (sequence order preserved)
df = df.sort_values('Date').reset_index(drop=True)
df['Cum P&L'] = df['P&L'].fillna(0).cumsum()
df['Running Max'] = df['Cum P&L'].cummax()
df['Drawdown'] = df['Cum P&L'] - df['Running Max']

# =========================================================
# HEADER + TICKER
# =========================================================
st.markdown("# 📈 FX Performance Terminal")

ticker_items = ""
for _, r in df.sort_values('Date', ascending=False).head(30).iterrows():
    color = "#22c55e" if r['W/L'] == 'Won' else "#ef4444"
    sign = "+" if (r['P&L'] or 0) >= 0 else ""
    pnl_txt = f"{sign}{r['P&L']:.2f}" if pd.notna(r['P&L']) else "—"
    ticker_items += (
        f"<span class='ticker-item'>{r['Date'].strftime('%d %b')} · "
        f"<b>{r['Pair']}</b> {r['Action']} "
        f"<span style='color:{color}'>{pnl_txt}</span></span>"
    )
st.markdown(
    f"<div class='ticker-wrap'><div class='ticker-move'>{ticker_items}{ticker_items}</div></div>",
    unsafe_allow_html=True,
)

# =========================================================
# KEY STATS
# =========================================================
total_trades = len(df)
wins = int(df['Win'].sum())
losses = total_trades - wins
win_rate = (wins / total_trades * 100) if total_trades else 0
total_pnl = df['P&L'].sum()
avg_rr = df['R Multiple'].mean()
gross_profit = df.loc[df['P&L'] > 0, 'P&L'].sum()
gross_loss = abs(df.loc[df['P&L'] < 0, 'P&L'].sum())
profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else np.nan
max_dd = df['Drawdown'].min()
daily_pnl = df.groupby(df['Date'].dt.date)['P&L'].sum()
sharpe = (daily_pnl.mean() / daily_pnl.std() * np.sqrt(252)) if daily_pnl.std() not in (0, np.nan) else np.nan

# current streak
streak, streak_type = 0, None
for w in df['Win'].iloc[::-1]:
    cur = 'W' if w == 1 else 'L'
    if streak_type is None:
        streak_type = cur
        streak = 1
    elif cur == streak_type:
        streak += 1
    else:
        break

def fmt_money(x):
    if pd.isna(x):
        return "—"
    cls = "green" if x >= 0 else "red"
    sign = "+" if x >= 0 else ""
    return f"<span class='stat-value {cls}'>{sign}{x:,.2f}</span>"

def stat_card(label, value_html):
    st.markdown(
        f"<div class='stat-card'><div class='stat-label'>{label}</div>{value_html}</div>",
        unsafe_allow_html=True,
    )

c1, c2, c3, c4, c5, c6 = st.columns(6)
with c1:
    stat_card("Total P&L", fmt_money(total_pnl))
with c2:
    stat_card("Win Rate", f"<span class='stat-value neutral'>{win_rate:.1f}%</span>")
with c3:
    stat_card("Total Trades", f"<span class='stat-value neutral'>{total_trades}</span> "
                               f"<span style='color:#8b93a3;font-size:13px'>({wins}W / {losses}L)</span>")
with c4:
    stat_card("Avg R-Multiple", f"<span class='stat-value {'green' if (avg_rr or 0) >= 0 else 'red'}'>"
                                 f"{avg_rr:.2f}R</span>" if pd.notna(avg_rr) else "<span class='stat-value neutral'>—</span>")
with c5:
    stat_card("Profit Factor", f"<span class='stat-value neutral'>{profit_factor:.2f}</span>" if pd.notna(profit_factor) else "<span class='stat-value neutral'>—</span>")
with c6:
    stat_card("Max Drawdown", f"<span class='stat-value red'>{max_dd:,.2f}</span>")

c7, c8, c9 = st.columns(3)
with c7:
    stat_card("Sharpe (annualized)", f"<span class='stat-value neutral'>{sharpe:.2f}</span>" if pd.notna(sharpe) else "<span class='stat-value neutral'>—</span>")
with c8:
    streak_color = "green" if streak_type == 'W' else "red"
    stat_card("Current Streak", f"<span class='stat-value {streak_color}'>{streak}{streak_type or ''}</span>")
with c9:
    stat_card("Avg Win / Avg Loss", f"<span class='stat-value neutral'>"
              f"{df.loc[df['Win']==1,'P&L'].mean():.1f} / {df.loc[df['Win']==0,'P&L'].mean():.1f}</span>"
              if wins and losses else "<span class='stat-value neutral'>—</span>")

st.markdown("<br>", unsafe_allow_html=True)

# =========================================================
# EQUITY CURVE + DRAWDOWN
# =========================================================
col_left, col_right = st.columns(2)

with col_left:
    st.markdown("### Equity Curve")
    fig_eq = go.Figure()
    fig_eq.add_trace(go.Scatter(
        x=df['Date'], y=df['Cum P&L'], mode='lines',
        line=dict(color='#22c55e', width=2),
        fill='tozeroy', fillcolor='rgba(34,197,94,0.08)',
        name='Cumulative P&L'
    ))
    fig_eq.update_layout(
        template='plotly_dark', paper_bgcolor='#0a0e14', plot_bgcolor='#0a0e14',
        height=340, margin=dict(l=10, r=10, t=10, b=10),
        xaxis_title=None, yaxis_title="Cumulative P&L",
    )
    st.plotly_chart(fig_eq, use_container_width=True)

with col_right:
    st.markdown("### Drawdown")
    fig_dd = go.Figure()
    fig_dd.add_trace(go.Scatter(
        x=df['Date'], y=df['Drawdown'], mode='lines',
        line=dict(color='#ef4444', width=2),
        fill='tozeroy', fillcolor='rgba(239,68,68,0.12)',
        name='Drawdown'
    ))
    fig_dd.update_layout(
        template='plotly_dark', paper_bgcolor='#0a0e14', plot_bgcolor='#0a0e14',
        height=340, margin=dict(l=10, r=10, t=10, b=10),
        xaxis_title=None, yaxis_title="Drawdown",
    )
    st.plotly_chart(fig_dd, use_container_width=True)

# =========================================================
# R-MULTIPLE DISTRIBUTION + MONTHLY P&L
# =========================================================
col_left2, col_right2 = st.columns(2)

with col_left2:
    st.markdown("### R-Multiple Distribution")
    r_data = df['R Multiple'].dropna()
    if len(r_data):
        fig_r = px.histogram(r_data, nbins=30, color_discrete_sequence=['#3b82f6'])
        fig_r.update_layout(
            template='plotly_dark', paper_bgcolor='#0a0e14', plot_bgcolor='#0a0e14',
            height=320, margin=dict(l=10, r=10, t=10, b=10),
            showlegend=False, xaxis_title="R Multiple", yaxis_title="Trades",
        )
        fig_r.add_vline(x=0, line_dash="dash", line_color="#6b7280")
        st.plotly_chart(fig_r, use_container_width=True)
    else:
        st.info("No R-multiple data available for the current filter selection.")

with col_right2:
    st.markdown("### Monthly P&L")
    monthly = df.groupby(df['Date'].dt.to_period('M'))['P&L'].sum()
    monthly.index = monthly.index.to_timestamp()
    colors = ['#22c55e' if v >= 0 else '#ef4444' for v in monthly.values]
    fig_m = go.Figure(go.Bar(x=monthly.index, y=monthly.values, marker_color=colors))
    fig_m.update_layout(
        template='plotly_dark', paper_bgcolor='#0a0e14', plot_bgcolor='#0a0e14',
        height=320, margin=dict(l=10, r=10, t=10, b=10),
        xaxis_title=None, yaxis_title="P&L",
    )
    st.plotly_chart(fig_m, use_container_width=True)

# =========================================================
# SETUP / MODEL PERFORMANCE
# =========================================================
st.markdown("### Setup Performance (by Model)")
setup_perf = df.groupby('Model').agg(
    Trades=('P&L', 'count'),
    Wins=('Win', 'sum'),
    Total_PnL=('P&L', 'sum'),
    Avg_RR=('R Multiple', 'mean'),
).reset_index()
setup_perf['Win Rate %'] = (setup_perf['Wins'] / setup_perf['Trades'] * 100).round(1)
setup_perf = setup_perf.sort_values('Total_PnL', ascending=False)

col_s1, col_s2 = st.columns([1.3, 1])
with col_s1:
    fig_setup = go.Figure(go.Bar(
        x=setup_perf['Model'], y=setup_perf['Total_PnL'],
        marker_color=['#22c55e' if v >= 0 else '#ef4444' for v in setup_perf['Total_PnL']],
        text=setup_perf['Win Rate %'].astype(str) + '% WR',
        textposition='outside',
    ))
    fig_setup.update_layout(
        template='plotly_dark', paper_bgcolor='#0a0e14', plot_bgcolor='#0a0e14',
        height=320, margin=dict(l=10, r=10, t=30, b=10),
        xaxis_title=None, yaxis_title="Total P&L",
    )
    st.plotly_chart(fig_setup, use_container_width=True)
with col_s2:
    st.dataframe(
        setup_perf.rename(columns={'Total_PnL': 'Total P&L', 'Avg_RR': 'Avg R'})
        .style.format({'Total P&L': '{:,.2f}', 'Avg R': '{:.2f}', 'Win Rate %': '{:.1f}'}),
        use_container_width=True, hide_index=True, height=320,
    )

# =========================================================
# RECENT TRADES TABLE
# =========================================================
st.markdown("### Recent Trades")
show_cols = ['Date', 'Pair', 'Action', 'Session', 'W/L', 'Lot', 'Pip', 'P&L',
             'R Multiple', 'RR', 'Setup', 'Model', 'Why']
display_df = df.sort_values('Date', ascending=False)[show_cols].copy()
display_df['Date'] = display_df['Date'].dt.strftime('%d %b %Y')

st.dataframe(
    display_df.style.format({'P&L': '{:,.2f}', 'R Multiple': '{:.2f}', 'RR': '{:.2f}', 'Pip': '{:.1f}'})
    .map(lambda v: 'color: #22c55e' if v == 'Won' else ('color: #ef4444' if v == 'Loss' else ''), subset=['W/L']),
    use_container_width=True, hide_index=True, height=420,
)

st.caption(f"Showing {total_trades} trades matching current filters · Data source refreshes every 5 minutes from Google Sheets.")
