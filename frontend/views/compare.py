"""Compare: exact SEC figures across companies. No AI on this page - Python does everything."""
import altair as alt
import pandas as pd
import streamlit as st

from frontend import api_client, ui
from frontend.api_client import ApiError

ui.page_header(ui.finsight_mark(44), "Compare Companies",
               "Exact figures from SEC XBRL Company Facts. Ranked, compared and charted by Python; no AI involved.")

try:
    metric_list = ui.metrics()
    companies = ui.companies()
except ApiError as exc:
    st.error(exc.message)
    st.stop()

labels = {m["label"]: m["metric"] for m in metric_list}
names = {c["ticker"]: c["name"] for c in companies}
c1, c2 = st.columns([1, 2])
metric_label = c1.selectbox("Metric", list(labels))
chosen = c2.multiselect("Companies", ui.TICKERS, default=ui.TICKERS, format_func=lambda t: f"{names.get(t, t)} ({t})")
metric = labels[metric_label]

if len(chosen) < 2:
    st.info("Choose at least 2 companies.")
    st.stop()

tab_rank, tab_trend = st.tabs(["🏆 Latest fiscal year", "📈 5-year trend"])

with tab_rank:
    try:
        result = api_client.compare(chosen, metric, None)
        ui.render_comparison(result, chart=True, key="cmp")
        if result["rows"]:
            csv = pd.DataFrame(result["rows"]).to_csv(index=False).encode("utf-8")
            st.download_button("⬇ Download table (CSV)", csv, file_name=f"finsight_{metric}_comparison.csv",
                               mime="text/csv")
    except ApiError as exc:
        st.error(exc.message)

with tab_trend:
    rows, missing = [], []
    for t in chosen:
        try:
            history = ui.metric_history(ui.financials(t), metric)
        except ApiError as exc:
            st.error(exc.message)
            history = []
        if not history:
            missing.append(names.get(t, t))
        for r in history:
            rows.append({"Company": t, "Fiscal year": r["fiscal_year"], "USD billions": round(r["value"] / 1e9, 2),
                         "Value": r["value_display"], "YoY %": r.get("yoy_change_pct"),
                         "Period end": r["period_end"]})
    if rows:
        df = pd.DataFrame(rows)
        colors = alt.Scale(domain=chosen, range=[ui.BRAND_COLORS[t] for t in chosen])
        chart = (alt.Chart(df).mark_line(point=alt.OverlayMarkDef(size=70), strokeWidth=3)
                 .encode(x=alt.X("Fiscal year:O", title="Fiscal year", axis=alt.Axis(labelAngle=0)),
                         y=alt.Y("USD billions:Q", title=f"{metric_label} (USD billions)"),
                         color=alt.Color("Company:N", scale=colors, legend=alt.Legend(orient="top")),
                         tooltip=["Company", "Fiscal year", "Value", "YoY %", "Period end"])
                 .properties(height=380))
        with st.container(border=True):
            st.markdown(f"**{metric_label} · last 5 fiscal years**")
            st.altair_chart(chart, width="stretch")
        pivot = df.pivot_table(index="Company", columns="Fiscal year", values="USD billions")
        pivot = pivot.apply(lambda col: col.map(lambda v: f"${v:,.2f}B" if pd.notna(v) else "—"))
        st.dataframe(pivot, width="stretch")
        st.caption("Each company's own fiscal years (they end on different dates). Hover a point for details.")
    for name in missing:
        st.caption(f"ℹ️ {name} does not report {metric_label.lower()} in its SEC XBRL data.")
