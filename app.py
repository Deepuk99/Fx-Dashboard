import calendar as pycal
import csv
import io
from datetime import date

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import requests
import streamlit as st

# =========================================================
# CONFIG
# =========================================================
CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vS17geJblGtzfcq5AYKaaRakdMtFpuHKaE_H-vg1BndiU1qV02hkH5BZiPA1qpbZExCH_nh5X9jUi_W/pub?gid=438761626&single=true&output=csv"
APP_TITLE = "dpkFXdashboard"

st.set_page_config(page_title=APP_TITLE, page_icon="📈", layout="wide")

# =========================================================
# THEME — TradeZella-style: dark navy + purple accent,
# green/red P&L, clean geometric sans font
# =========================================================
THEMES = {
    "Dark": dict(
        bg="#0b0d17", card_bg="#141726", card_bg2="#10121f", border="#232640",
        text_primary="#f1f2f6", text_secondary="#8b8fa3", ticker_bg="#10121f",
        green="#17c68f", red="#ff4d67", purple="#8b5cf6", purple_soft="rgba(139,92,246,0.12)",
        plotly_template="plotly_dark", plot_bg="#0b0d17",
    ),
    "Light": dict(
        bg="#f6f6fb", card_bg="#ffffff", card_bg2="#ffffff", border="#e6e6f2",
        text_primary="#14141f", text_secondary="#6b6f83", ticker_bg="#ffffff",
        green="#0ea672", red="#e5364f", purple="#7c5cfc", purple_soft="rgba(124,92,252,0.10)",
        plotly_template="plotly_white", plot_bg="#ffffff",
    ),
}

if "theme" not in st.session_state:
    st.session_state.theme = "Dark"
T = THEMES[st.session_state.theme]

st.markdown(f"""
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
    html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"],
    [data-testid="stToolbar"], .main, .block-container {{
        background-color: {T['bg']} !important;
        color: {T['text_primary']} !important;
        font-family: 'Inter', sans-serif !important;
    }}
    h1, h2, h3, h4, p, span, label, div {{ color: {T['text_primary']}; font-family: 'Inter', sans-serif; }}
    h1, h2, h3 {{ font-weight: 800; letter-spacing: -0.5px; }}

    .kpi-card {{
        background: {T['card_bg']};
        border: 1px solid {T['border']};
        border-radius: 14px;
        padding: 16px 18px;
        margin-bottom: 10px;
    }}
    .kpi-label {{ color: {T['text_secondary']}; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.6px; margin-bottom: 6px; }}
    .kpi-value {{ font-size: 25px; font-weight: 800; }}
    .kpi-sub {{ font-size: 12px; color: {T['text_secondary']}; margin-top: 2px; }}
    .green {{ color: {T['green']}; }}
    .red {{ color: {T['red']}; }}
    .purple {{ color: {T['purple']}; }}
    .neutral {{ color: {T['text_primary']}; }}

    .ticker-wrap {{
        width: 100%; overflow: hidden; background: {T['ticker_bg']};
        border-top: 1px solid {T['border']}; border-bottom: 1px solid {T['border']};
        padding: 10px 0; margin-bottom: 20px; border-radius: 10px;
    }}
    .ticker-move {{
        display: inline-block; white-space: nowrap;
        animation: ticker 140s linear infinite;
        font-size: 13px; font-weight: 500;
    }}
    .ticker-wrap:hover .ticker-move {{ animation-play-state: paused; }}
    @keyframes ticker {{ 0% {{ transform: translateX(0); }} 100% {{ transform: translateX(-50%); }} }}
    .ticker-item {{ display: inline-block; padding: 0 24px; }}

    div[data-testid="stDataFrame"] {{ border: 1px solid {T['border']}; border-radius: 12px; }}
    div[data-testid="stExpander"] {{ background: {T['card_bg']}; border: 1px solid {T['border']}; border-radius: 14px; }}
    .stButton>button {{
        background: {T['purple']} !important; color: white !important; border: none !important;
        border-radius: 8px !important; font-weight: 600 !important;
    }}

    .cal-wrap {{ background: {T['card_bg']}; border: 1px solid {T['border']}; border-radius: 14px; padding: 14px; }}
    .cal-grid {{ display: grid; grid-template-columns: repeat(7, 1fr) 100px; gap: 6px; }}
    .cal-head {{ color: {T['text_secondary']}; font-size: 11px; font-weight: 700; text-transform: uppercase; text-align: center; padding: 4px 0; }}
    .cal-cell {{ border-radius: 8px; padding: 6px 8px; min-height: 64px; font-size: 11px; border: 1px solid transparent; }}
    .cal-cell .d {{ font-size: 11px; opacity: 0.6; }}
    .cal-cell .pnl {{ font-size: 14px; font-weight: 800; margin-top: 4px; }}
    .cal-cell .cnt {{ font-size: 10.5px; opacity: 0.75; margin-top: 2px; }}
    .cal-empty {{ background: transparent; }}
    .cal-week-total {{ background: {T['purple_soft']}; border-radius: 8px; padding: 6px 8px; min-height: 64px; font-size: 11px; }}
</style>
""", unsafe_allow_html=True)


def themed(fig):
    fig.update_layout(
        template=T['plotly_template'],
        paper_bgcolor=T['plot_bg'], plot_bgcolor=T['plot_bg'],
        font=dict(color=T['text_primary'], family='Inter'),
    )
    return fig


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

    df['Date'] = pd.to_datetime(df['Date'], format='%d/%m/%Y', errors='coerce')
    df = df[df['Date'].notna()]
    df = df[df['W/L'].isin(['Won', 'Loss'])]

    for col in ['Pip', 'Lot', 'Swap', 'Charges', 'P&L', 'Day Total', 'Actl Pft %',
                'TP', 'SL', 'RR', 'R Multiple']:
        df[col] = clean_numeric(df[col])

    df['Win'] = (df['W/L'] == 'Won').astype(int)
    df['Setup'] = df['Setup'].fillna('Unknown').replace('', 'Unknown')
    df['Model'] = df['Model'].fillna('N/A').replace('', 'N/A')
    df['Session'] = df['Session'].fillna('Unknown').replace('', 'Unknown')
    df['Pair'] = df['Pair'].fillna('Unknown').replace('', 'Unknown')
    df['Action'] = df['Action'].fillna('Unknown').replace('', 'Unknown')
    df['WK'] = df['WK'].fillna('N/A').replace('', 'N/A')
    df['Month'] = df['Date'].dt.to_period('M').dt.to_timestamp()

    df = df.sort_values('Date').reset_index(drop=True)
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
# HEADER
# =========================================================
h1, h2 = st.columns([5, 1])
with h1:
    st.markdown(f"# 📈 {APP_TITLE}")
with h2:
    choice = st.radio("Theme", ["Dark", "Light"], horizontal=True,
                       index=0 if st.session_state.theme == "Dark" else 1,
                       label_visibility="collapsed")
    if choice != st.session_state.theme:
        st.session_state.theme = choice
        st.rerun()

# =========================================================
# FILTERS
# =========================================================
with st.expander("⚙️ Filters", expanded=True):
    min_date, max_date = df_raw['Date'].min().date(), df_raw['Date'].max().date()

    fc1, fc2 = st.columns([1, 3])
    with fc1:
        date_range = st.date_input("Date range", value=(min_date, max_date),
                                    min_value=min_date, max_value=max_date)
    with fc2:
        if st.button("🔄 Force refresh now"):
            st.cache_data.clear()
            st.rerun()

    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date, end_date = min_date, max_date

    fr1, fr2, fr3, fr4 = st.columns(4)
    with fr1:
        pairs = sorted(df_raw['Pair'].unique())
        sel_pairs = st.multiselect("Currency Pair", pairs, default=pairs)
        models = sorted(df_raw['Model'].unique())
        sel_models = st.multiselect("Setup / Model", models, default=models)
    with fr2:
        setups = sorted(df_raw['Setup'].unique())
        sel_setups = st.multiselect("Trade Type", setups, default=setups)
        sessions = sorted(df_raw['Session'].unique())
        sel_sessions = st.multiselect("Session", sessions, default=sessions)
    with fr3:
        actions = sorted(df_raw['Action'].unique())
        sel_actions = st.multiselect("Action", actions, default=actions)
        wl_options = ['Won', 'Loss']
        sel_wl = st.multiselect("Result", wl_options, default=wl_options)
    with fr4:
        st.caption(f"Latest data point in sheet: **{max_date}**")
        st.caption("Data auto-refreshes every 5 minutes.")

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
    st.warning("No trades match the current filters. Adjust filters above.")
    st.stop()

df = df.sort_values('Date').reset_index(drop=True)
df['Cum P&L'] = df['P&L'].fillna(0).cumsum()
df['Running Max'] = df['Cum P&L'].cummax()
df['Drawdown'] = df['Cum P&L'] - df['Running Max']

# =========================================================
# TICKER
# =========================================================
ticker_items = ""
for _, r in df.sort_values('Date', ascending=False).head(30).iterrows():
    color = T['green'] if r['W/L'] == 'Won' else T['red']
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

daily_pnl_series = df.groupby(df['Date'].dt.date)['P&L'].sum()
sharpe = (daily_pnl_series.mean() / daily_pnl_series.std() * np.sqrt(252)) if daily_pnl_series.std() not in (0, np.nan) else np.nan
day_win_rate = (daily_pnl_series > 0).mean() * 100 if len(daily_pnl_series) else np.nan

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
        return "<span class='kpi-value neutral'>—</span>"
    cls = "green" if x >= 0 else "red"
    sign = "+" if x >= 0 else ""
    return f"<span class='kpi-value {cls}'>{sign}{x:,.2f}</span>"


def kpi_card(label, value_html, sub=""):
    sub_html = f"<div class='kpi-sub'>{sub}</div>" if sub else ""
    st.markdown(
        f"<div class='kpi-card'><div class='kpi-label'>{label}</div>{value_html}{sub_html}</div>",
        unsafe_allow_html=True,
    )


c1, c2, c3, c4, c5, c6 = st.columns(6)
with c1:
    kpi_card("Net P&L", fmt_money(total_pnl))
with c2:
    kpi_card("Win Rate", f"<span class='kpi-value purple'>{win_rate:.1f}%</span>", f"{wins}W / {losses}L")
with c3:
    kpi_card("Profit Factor",
              f"<span class='kpi-value neutral'>{profit_factor:.2f}</span>" if pd.notna(profit_factor)
              else "<span class='kpi-value neutral'>—</span>")
with c4:
    kpi_card("Day Win %",
              f"<span class='kpi-value neutral'>{day_win_rate:.1f}%</span>" if pd.notna(day_win_rate)
              else "<span class='kpi-value neutral'>—</span>", f"{len(daily_pnl_series)} trading days")
with c5:
    avg_win_loss = (f"{df.loc[df['Win']==1,'P&L'].mean():.1f} / {df.loc[df['Win']==0,'P&L'].mean():.1f}"
                     if wins and losses else "—")
    kpi_card("Avg Win / Avg Loss", f"<span class='kpi-value neutral'>{avg_win_loss}</span>")
with c6:
    kpi_card("Max Drawdown", f"<span class='kpi-value red'>{max_dd:,.2f}</span>")

c7, c8, c9 = st.columns(3)
with c7:
    kpi_card("Avg R-Multiple",
              f"<span class='kpi-value {'green' if (avg_rr or 0) >= 0 else 'red'}'>{avg_rr:.2f}R</span>"
              if pd.notna(avg_rr) else "<span class='kpi-value neutral'>—</span>")
with c8:
    kpi_card("Sharpe (annualized)",
              f"<span class='kpi-value neutral'>{sharpe:.2f}</span>" if pd.notna(sharpe)
              else "<span class='kpi-value neutral'>—</span>")
with c9:
    streak_color = "green" if streak_type == 'W' else "red"
    kpi_card("Current Streak", f"<span class='kpi-value {streak_color}'>{streak}{streak_type or ''}</span>")

st.markdown("<br>", unsafe_allow_html=True)

# =========================================================
# BIG EQUITY CURVE (purple/green gradient, TradeZella-style hero chart)
# =========================================================
st.markdown("### Net Cumulative P&L")
fig_eq = go.Figure()
fig_eq.add_trace(go.Scatter(
    x=df['Date'], y=df['Cum P&L'], mode='lines',
    line=dict(color=T['purple'], width=3),
    fill='tozeroy', fillcolor='rgba(139,92,246,0.14)',
    name='Cumulative P&L'
))
themed(fig_eq).update_layout(height=380, margin=dict(l=10, r=10, t=10, b=10), yaxis_title="Cumulative P&L")
st.plotly_chart(fig_eq, use_container_width=True)

# =========================================================
# WIN RATE DONUT + DRAWDOWN
# =========================================================
col_left, col_right = st.columns([1, 2])

with col_left:
    st.markdown("### Win Rate")
    fig_donut = go.Figure(go.Pie(
        values=[wins, losses], labels=['Wins', 'Losses'], hole=0.72,
        marker_colors=[T['green'], T['red']], textinfo='none', sort=False,
    ))
    fig_donut.add_annotation(text=f"<b>{win_rate:.1f}%</b><br><span style='font-size:11px'>Win Rate</span>",
                              showarrow=False, font=dict(size=20, color=T['text_primary']))
    themed(fig_donut).update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10), showlegend=True,
                                     legend=dict(orientation='h', y=-0.1))
    st.plotly_chart(fig_donut, use_container_width=True)

with col_right:
    st.markdown("### Drawdown")
    fig_dd = go.Figure()
    fig_dd.add_trace(go.Scatter(
        x=df['Date'], y=df['Drawdown'], mode='lines',
        line=dict(color=T['red'], width=2),
        fill='tozeroy', fillcolor='rgba(255,77,103,0.12)',
        name='Drawdown'
    ))
    themed(fig_dd).update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10), yaxis_title="Drawdown")
    st.plotly_chart(fig_dd, use_container_width=True)

# =========================================================
# WEEK-WISE PERFORMANCE
# =========================================================
st.markdown("### Week-wise Performance")

week_order = df.groupby('WK')['Date'].min().sort_values().index.tolist()
weekly = df.groupby('WK').agg(
    Trades=('P&L', 'count'), Wins=('Win', 'sum'), PnL=('P&L', 'sum'),
    WeekStart=('Date', 'min'), WeekEnd=('Date', 'max'),
).reindex(week_order).reset_index()
weekly['Win Rate %'] = (weekly['Wins'] / weekly['Trades'] * 100).round(1)

fig_week = go.Figure()
fig_week.add_trace(go.Bar(
    x=weekly['WK'], y=weekly['PnL'], name='P&L',
    marker_color=[T['green'] if v >= 0 else T['red'] for v in weekly['PnL']],
    yaxis='y1',
))
fig_week.add_trace(go.Scatter(
    x=weekly['WK'], y=weekly['Trades'], name='Trades',
    mode='lines+markers', line=dict(color=T['purple'], width=2),
    yaxis='y2',
))
themed(fig_week).update_layout(
    height=340, margin=dict(l=10, r=10, t=30, b=10),
    yaxis=dict(title='P&L'),
    yaxis2=dict(title='Trades', overlaying='y', side='right', showgrid=False),
    legend=dict(orientation='h', y=1.1),
)
st.plotly_chart(fig_week, use_container_width=True)

with st.expander("Week-wise data table"):
    wk_table = weekly.copy()
    wk_table['WeekStart'] = wk_table['WeekStart'].dt.strftime('%d %b %Y')
    wk_table['WeekEnd'] = wk_table['WeekEnd'].dt.strftime('%d %b %Y')
    st.dataframe(
        wk_table[['WK', 'WeekStart', 'WeekEnd', 'Trades', 'Wins', 'Win Rate %', 'PnL']]
        .rename(columns={'PnL': 'P&L'})
        .style.format({'P&L': '{:,.2f}', 'Win Rate %': '{:.1f}'}),
        use_container_width=True, hide_index=True,
    )

# =========================================================
# CALENDAR — real month-grid view (TradeZella style)
# =========================================================
st.markdown("### Calendar")

daily = df.groupby(df['Date'].dt.normalize()).agg(
    Trades=('P&L', 'count'), PnL=('P&L', 'sum')
).reset_index().rename(columns={'Date': 'Day'})
daily_map = {row['Day'].date(): (row['Trades'], row['PnL']) for _, row in daily.iterrows()}

available_months = sorted(df['Date'].dt.to_period('M').unique())
month_labels = [m.strftime('%B %Y') for m in available_months]

if "cal_month_idx" not in st.session_state or st.session_state.cal_month_idx >= len(available_months):
    st.session_state.cal_month_idx = len(available_months) - 1

nav1, nav2, nav3 = st.columns([1, 3, 1])
with nav1:
    if st.button("◀ Prev") and st.session_state.cal_month_idx > 0:
        st.session_state.cal_month_idx -= 1
        st.rerun()
with nav3:
    if st.button("Next ▶") and st.session_state.cal_month_idx < len(available_months) - 1:
        st.session_state.cal_month_idx += 1
        st.rerun()
with nav2:
    st.markdown(f"<h4 style='text-align:center'>{month_labels[st.session_state.cal_month_idx]}</h4>",
                unsafe_allow_html=True)

sel_period = available_months[st.session_state.cal_month_idx]
year, month = sel_period.year, sel_period.month

cal_obj = pycal.Calendar(firstweekday=6)  # Sunday-first, like TradeZella
month_weeks = cal_obj.monthdatescalendar(year, month)

max_abs_day = max([abs(v[1]) for v in daily_map.values()] + [1])


def cell_style(pnl):
    if pnl is None:
        return f"background: transparent; border: 1px solid {T['border']};"
    intensity = min(abs(pnl) / max_abs_day, 1) * 0.35 + 0.08
    if pnl >= 0:
        return f"background: rgba(23,198,143,{intensity}); border: 1px solid {T['green']};"
    return f"background: rgba(255,77,103,{intensity}); border: 1px solid {T['red']};"


html = "<div class='cal-wrap'><div class='cal-grid'>"
for wd in ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']:
    html += f"<div class='cal-head'>{wd}</div>"
html += "<div class='cal-head'>Week</div>"

for week in month_weeks:
    week_pnl, week_trades = 0.0, 0
    for d in week:
        if d.month != month:
            html += "<div class='cal-cell cal-empty'></div>"
            continue
        trades, pnl = daily_map.get(d, (0, None))
        if trades and trades > 0:
            week_pnl += pnl
            week_trades += trades
            color_cls = 'green' if pnl >= 0 else 'red'
            html += (f"<div class='cal-cell' style='{cell_style(pnl)}'>"
                      f"<div class='d'>{d.day}</div>"
                      f"<div class='pnl {color_cls}'>{pnl:+.0f}</div>"
                      f"<div class='cnt'>{int(trades)} trade{'s' if trades != 1 else ''}</div></div>")
        else:
            html += (f"<div class='cal-cell' style='{cell_style(None)}'>"
                      f"<div class='d'>{d.day}</div></div>")
    wk_color_cls = 'green' if week_pnl >= 0 else 'red'
    if week_trades:
        html += (f"<div class='cal-week-total'><div class='d'>Total</div>"
                  f"<div class='pnl {wk_color_cls}'>{week_pnl:+.0f}</div>"
                  f"<div class='cnt'>{week_trades} trades</div></div>")
    else:
        html += "<div class='cal-week-total'></div>"

html += "</div></div>"
st.markdown(html, unsafe_allow_html=True)

with st.expander("Monthly subtotals (all months in filter)"):
    monthly_sub = df.groupby(df['Date'].dt.to_period('M')).agg(
        Trades=('P&L', 'count'), PnL=('P&L', 'sum')
    ).reset_index()
    monthly_sub['Date'] = monthly_sub['Date'].astype(str)
    st.dataframe(
        monthly_sub.rename(columns={'Date': 'Month', 'PnL': 'P&L'})
        .style.format({'P&L': '{:,.2f}'}),
        use_container_width=True, hide_index=True,
    )

# =========================================================
# R-MULTIPLE DISTRIBUTION + MONTHLY P&L
# =========================================================
col_left2, col_right2 = st.columns(2)

with col_left2:
    st.markdown("### R-Multiple Distribution")
    r_data = df['R Multiple'].dropna()
    if len(r_data):
        fig_r = px.histogram(r_data, nbins=30, color_discrete_sequence=[T['purple']])
        themed(fig_r).update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10),
                                     showlegend=False, xaxis_title="R Multiple", yaxis_title="Trades")
        fig_r.add_vline(x=0, line_dash="dash", line_color=T['text_secondary'])
        st.plotly_chart(fig_r, use_container_width=True)
    else:
        st.info("No R-multiple data available for the current filter selection.")

with col_right2:
    st.markdown("### Monthly P&L")
    monthly = df.groupby(df['Date'].dt.to_period('M'))['P&L'].sum()
    monthly.index = monthly.index.to_timestamp()
    colors = [T['green'] if v >= 0 else T['red'] for v in monthly.values]
    fig_m = go.Figure(go.Bar(x=monthly.index, y=monthly.values, marker_color=colors))
    themed(fig_m).update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10), yaxis_title="P&L")
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
        marker_color=[T['green'] if v >= 0 else T['red'] for v in setup_perf['Total_PnL']],
        text=setup_perf['Win Rate %'].astype(str) + '% WR',
        textposition='outside',
    ))
    themed(fig_setup).update_layout(height=320, margin=dict(l=10, r=10, t=30, b=10), yaxis_title="Total P&L")
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
    .map(lambda v: f"color: {T['green']}" if v == 'Won' else (f"color: {T['red']}" if v == 'Loss' else ''),
         subset=['W/L']),
    use_container_width=True, hide_index=True, height=420,
)

st.caption(f"Showing {total_trades} trades matching current filters · Data source refreshes every 5 minutes from Google Sheets.")
