"""Company Dashboard: one company's key figures, trends and Python-generated insights."""
import html

import altair as alt
import pandas as pd
import streamlit as st

from frontend import ui
from frontend.api_client import ApiError

companies = {c["ticker"]: c for c in ui.companies()}
wanted = st.session_state.get("dash_ticker", "AAPL")
wanted = wanted if wanted in ui.TICKERS else "AAPL"
# A stable key, set only on the first visit or when Home's "Dashboard →" asked for another company.
# (Passing a changing default= instead makes Streamlit rebuild the widget and drop every second click.)
if st.session_state.get("dash_last") != wanted or st.session_state.get("dash_pick") not in ui.TICKERS:
    st.session_state.dash_pick = wanted
ticker = st.segmented_control("Company", ui.TICKERS, key="dash_pick",
                              format_func=lambda t: companies.get(t, {}).get("name", t),
                              label_visibility="collapsed") or wanted
st.session_state.dash_ticker = st.session_state.dash_last = ticker

try:
    fin = ui.financials(ticker)
except ApiError as exc:
    st.error(exc.message)
    st.stop()

rev = ui.latest(fin, "revenue")
period = f"FY{rev['fiscal_year']} · period ending {rev['period_end']}" if rev else ""
st.markdown(f"<div class='fs-brand' style='margin:6px 0 12px'>{ui.company_logo_img(ticker, 46)}<div>"
            f"<div style='font-size:1.75rem;font-weight:800;color:#EEF2FA'>{html.escape(fin['company'])} ({ticker})</div>"
            f"<div class='fs-muted'>{period} · exact values from SEC XBRL Company Facts</div></div></div>",
            unsafe_allow_html=True)
if st.button(f"📑 Full company report for {fin['company']}", type="primary"):
    st.session_state.ask_pending = f"Company report of {fin['company']}"
    st.switch_page("views/ask.py")


def kpi(col, label: str, metric: str) -> None:
    row = ui.latest(fin, metric)
    value = row["value_display"] if row else "not reported"
    delta = ui.delta_html(row.get("yoy_change_pct")) if row else ""
    derived = " <span class='fs-muted'>(derived)</span>" if row and row.get("derived") else ""
    col.markdown(f"<div class='fs-card fs-kpi'><div class='v'>{value}</div><div class='l'>{label}{derived}</div>"
                 f"{delta}</div>", unsafe_allow_html=True)


def margin(metric: str) -> tuple[float | None, float | None]:
    """Margin % for the latest and previous year, calculated here by Python from exact values."""
    num = {r["fiscal_year"]: r["value"] for r in ui.metric_history(fin, metric)}
    den = {r["fiscal_year"]: r["value"] for r in ui.metric_history(fin, "revenue")}
    years = sorted(set(num) & set(den))
    pct = [num[y] / den[y] * 100 for y in years if den[y]]
    return (pct[-1] if pct else None), (pct[-2] if len(pct) > 1 else None)


k = st.columns(4)
kpi(k[0], "Revenue", "revenue")
kpi(k[1], "Net income", "net_income")
net_m, net_prev = margin("net_income")
pp = f"<span class='{'fs-up' if (net_m or 0) >= (net_prev or 0) else 'fs-down'}'>{'▲' if (net_m or 0) >= (net_prev or 0) else '▼'} " \
     f"{abs((net_m or 0) - (net_prev or 0)):.1f} pts YoY</span>" if net_m is not None and net_prev is not None else ""
k[2].markdown(f"<div class='fs-card fs-kpi'><div class='v'>{f'{net_m:.1f}%' if net_m is not None else '—'}</div>"
              f"<div class='l'>Net profit margin</div>{pp}</div>", unsafe_allow_html=True)
kpi(k[3], "Operating cash flow", "operating_cash_flow")
st.write("")
k2 = st.columns(4)
kpi(k2[0], "Operating income", "operating_income")
kpi(k2[1], "Gross profit", "gross_profit")
kpi(k2[2], "Total assets", "total_assets")
kpi(k2[3], "Cash & equivalents", "cash")

left, right = st.columns([3, 2], gap="large")
with left:
    rows = []
    for metric, label in [("revenue", "Revenue"), ("operating_income", "Operating income"), ("net_income", "Net income")]:
        for r in ui.metric_history(fin, metric):
            rows.append({"Metric": label, "Fiscal year": r["fiscal_year"], "USD billions": round(r["value"] / 1e9, 2),
                         "Value": r["value_display"], "YoY %": r.get("yoy_change_pct")})
    with st.container(border=True):
        st.markdown("**Revenue and profit · last 5 fiscal years**")
        if rows:
            chart = (alt.Chart(pd.DataFrame(rows)).mark_line(point=alt.OverlayMarkDef(size=70), strokeWidth=3)
                     .encode(x=alt.X("Fiscal year:O", axis=alt.Axis(labelAngle=0)), y=alt.Y("USD billions:Q"),
                             color=alt.Color("Metric:N", scale=alt.Scale(
                                 domain=["Revenue", "Operating income", "Net income"],
                                 range=["#60A5FA", "#22D3EE", "#34D399"]),
                                             legend=alt.Legend(orient="top")),
                             tooltip=["Metric", "Fiscal year", "Value", "YoY %"]).properties(height=320))
            st.altair_chart(chart, width="stretch")

with right:
    with st.container(border=True):
        st.markdown("**Key insights** <span class='fs-muted'>· written by Python from the figures</span>",
                    unsafe_allow_html=True)
        insights = []
        for metric, label in [("revenue", "Revenue"), ("net_income", "Net income"),
                              ("operating_cash_flow", "Operating cash flow")]:
            row = ui.latest(fin, metric)
            if row and row.get("yoy_change_pct") is not None:
                verb = "grew" if row["yoy_change_pct"] >= 0 else "fell"
                insights.append(f"{label} {verb} **{abs(row['yoy_change_pct']):.1f}%** to "
                                f"**{row['value_display']}** in FY{row['fiscal_year']}.")
        if net_m is not None:
            insights.append(f"Net profit margin was **{net_m:.1f}%**"
                            + (f" (vs {net_prev:.1f}% the year before)." if net_prev is not None else "."))
        op_m, _ = margin("operating_income")
        if op_m is not None:
            insights.append(f"Operating margin was **{op_m:.1f}%**.")
        if not ui.latest(fin, "gross_profit"):
            insights.append("Gross profit is **not reported** in this company's XBRL data, so it isn't shown.")
        liab = ui.latest(fin, "total_liabilities")
        if liab and liab.get("derived"):
            insights.append("Total liabilities are **derived** (total liabilities & equity minus equity).")
        for text in insights:
            st.markdown(f"✅ {ui.safe_md(text)}")
        if rev:
            st.link_button("Open the latest 10-K filing on SEC ↗", rev["source_url"], width="stretch")

with st.expander("📋 All figures (5 fiscal years)"):
    table = []
    for m in fin["metrics"]:
        for r in m["history"]:
            table.append({"Metric": m["label"], "Fiscal year": f"FY{r['fiscal_year']}", "Value": r["value_display"],
                          "YoY %": r.get("yoy_change_pct"), "Period end": r["period_end"], "XBRL tag": r["tag"],
                          "Derived": "yes" if r.get("derived") else ""})
    st.dataframe(pd.DataFrame(table), hide_index=True, width="stretch")
