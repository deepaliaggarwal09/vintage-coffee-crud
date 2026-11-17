"""Dashboard page - the CA 1 analytics, now reading live from MySQL (no caching)."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from .. import db

# Categorical slots in fixed order (validated default palette, light mode)
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
MUTED = "#b9b8b2"
INK, GRID = "#0b0b0b", "#e6e5e0"


# ----------------------------------------------------------------------------
# data access (always live)
# ----------------------------------------------------------------------------
def _quarterly() -> pd.DataFrame:
    df = db.read_df("SELECT * FROM quarterly_results ORDER BY quarter_end")
    df["quarter_end"] = pd.to_datetime(df["quarter_end"])
    df["label"] = df["quarter_end"].dt.strftime("%b %Y")
    return df


def _annual() -> pd.DataFrame:
    return db.read_df("""
        SELECT f.year_id, f.year_label, f.fiscal_year_end,
               a.sales_cr, a.expenses_cr, a.net_profit_cr,
               b.reserves_cr, b.borrowings_cr,
               c.free_cash_flow_cr,
               r.cash_conversion_cycle, r.working_capital_days, r.roce_pct
        FROM fiscal_years f
        LEFT JOIN annual_pnl   a ON a.year_id = f.year_id
        LEFT JOIN balance_sheet b ON b.year_id = f.year_id
        LEFT JOIN cash_flows   c ON c.year_id = f.year_id
        LEFT JOIN ratios       r ON r.year_id = f.year_id
        ORDER BY f.fiscal_year_end""")


def _shareholding() -> pd.DataFrame:
    df = db.read_df("SELECT * FROM shareholding_pattern ORDER BY quarter_end")
    df["quarter_end"] = pd.to_datetime(df["quarter_end"])
    df["label"] = df["quarter_end"].dt.strftime("%b %Y")
    return df


def _peers() -> pd.DataFrame:
    return db.read_df("""
        SELECT c.company_name, c.is_vintage, p.*
        FROM peer_comparison p JOIN companies c ON c.company_id = p.company_id
        ORDER BY p.roce_pct DESC""")


# ----------------------------------------------------------------------------
# chart helpers
# ----------------------------------------------------------------------------
def _style(fig: go.Figure, title: str, y_title: str = "", legend: bool = True, height: int = 340):
    fig.update_layout(
        title=dict(text=title, x=0, font=dict(size=15, color=INK)),
        height=height, margin=dict(l=8, r=8, t=56, b=8),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#52514e", size=12),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1, title=None),
        showlegend=legend, hovermode="x unified", bargap=0.35,
    )
    fig.update_xaxes(showgrid=False, linecolor=GRID, ticks="outside", tickcolor=GRID)
    fig.update_yaxes(title=y_title, gridcolor=GRID, zeroline=True, zerolinecolor="#c9c8c2")
    return fig


def _show(fig: go.Figure, key: str) -> None:
    st.plotly_chart(fig, width="stretch", key=key, config={"displaylogo": False})


def _bars(df, x, ys: dict[str, tuple[str, str]], title, y_title, key, barmode="group", legend=None):
    fig = go.Figure()
    for col, (name, color) in ys.items():
        fig.add_bar(x=df[x], y=df[col], name=name, marker_color=color,
                    marker_line_color="rgba(0,0,0,0)")
    fig.update_layout(barmode=barmode)
    _style(fig, title, y_title, legend=len(ys) > 1 if legend is None else legend)
    _show(fig, key)


def _lines(df, x, ys: dict[str, tuple[str, str]], title, y_title, key, legend=None):
    fig = go.Figure()
    for col, (name, color) in ys.items():
        fig.add_scatter(x=df[x], y=df[col], name=name, mode="lines+markers",
                        line=dict(color=color, width=2), marker=dict(size=8, color=color,
                        line=dict(color="#fcfcfb", width=2)))
    _style(fig, title, y_title, legend=len(ys) > 1 if legend is None else legend)
    _show(fig, key)


def _delta(cur, prev, suffix="", pct=False):
    if pd.isna(cur) or pd.isna(prev):
        return None
    if pct:
        return f"{cur - prev:+.1f} pts"
    return f"{cur - prev:+,.2f}{suffix}"


# ----------------------------------------------------------------------------
# page
# ----------------------------------------------------------------------------
def render() -> None:
    st.title("☕ Vintage Coffee — Business Dashboard")
    st.caption("Live view of the MySQL database. Add, edit or delete data under **Manage records** and these charts update immediately.")

    q = _quarterly()
    a = _annual()
    s = _shareholding()
    p = _peers()

    if q.empty:
        st.warning("No quarterly data yet. Add rows under Manage records → Quarterly results.")
        return

    # ---- KPI cards (latest quarter vs previous) -------------------------------
    cur = q.iloc[-1]
    prev = q.iloc[-2] if len(q) > 1 else pd.Series(dtype=float)
    st.subheader(f"Latest quarter · {cur['label']}")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Sales", f"₹{cur['sales_cr']:,.0f} Cr", _delta(cur["sales_cr"], prev.get("sales_cr"), " Cr"))
    k2.metric("Net profit", f"₹{cur['net_profit_cr']:,.0f} Cr", _delta(cur["net_profit_cr"], prev.get("net_profit_cr"), " Cr"))
    k3.metric("Operating margin", f"{cur['opm_pct']:.1f}%", _delta(cur["opm_pct"], prev.get("opm_pct"), pct=True))
    k4.metric("EPS", f"₹{cur['eps_rs']:.2f}", _delta(cur["eps_rs"], prev.get("eps_rs")))

    # ---- filters ---------------------------------------------------------------
    with st.container(border=True):
        f1, f2 = st.columns(2)
        labels = q["label"].tolist()
        lo, hi = f1.select_slider("Quarter range", options=labels, value=(labels[0], labels[-1]))
        years = a["year_label"].tolist()
        chosen_years = f2.multiselect("Fiscal years", years, default=years)
    qf = q[(q["label"].map({l: i for i, l in enumerate(labels)}) >= labels.index(lo)) &
           (q["label"].map({l: i for i, l in enumerate(labels)}) <= labels.index(hi))]
    af = a[a["year_label"].isin(chosen_years)]
    sf = s[s["label"].isin(qf["label"])]

    t1, t2, t3, t4, t5 = st.tabs(["📈 Revenue & profit", "🏦 Balance sheet & cash",
                                  "⚙️ Efficiency", "👥 Shareholding", "🏆 Peers"])

    with t1:
        c1, c2 = st.columns(2)
        with c1:
            _bars(qf, "label", {"sales_cr": ("Sales", BLUE)}, "Quarterly sales", "₹ Cr", "q_sales")
        with c2:
            _bars(qf, "label", {"net_profit_cr": ("Net profit", AQUA)}, "Quarterly net profit", "₹ Cr", "q_np")
        c3, c4 = st.columns(2)
        with c3:
            _lines(qf, "label", {"opm_pct": ("OPM %", ORANGE)}, "Operating margin (OPM %)", "%", "q_opm")
        with c4:
            _bars(af, "year_label", {"sales_cr": ("Sales", BLUE), "expenses_cr": ("Expenses", ORANGE)},
                  "Annual sales vs expenses", "₹ Cr", "a_se")
        with st.expander("Quarterly data table"):
            st.dataframe(qf.drop(columns=["label"]), hide_index=True, width="stretch")

    with t2:
        c1, c2 = st.columns(2)
        with c1:
            _bars(af, "year_label", {"reserves_cr": ("Reserves", BLUE), "borrowings_cr": ("Borrowings", ORANGE)},
                  "Reserves vs borrowings", "₹ Cr", "bs_rb")
        with c2:
            _bars(af, "year_label", {"free_cash_flow_cr": ("Free cash flow", BLUE)},
                  "Free cash flow", "₹ Cr", "cf_fcf")

    with t3:
        c1, c2 = st.columns(2)
        with c1:
            _lines(af, "year_label", {"cash_conversion_cycle": ("Cash conversion cycle", BLUE),
                                      "working_capital_days": ("Working capital days", ORANGE)},
                   "Working-capital efficiency", "days", "r_days")
        with c2:
            _lines(af, "year_label", {"roce_pct": ("ROCE %", AQUA)}, "Return on capital employed", "%", "r_roce")

    with t4:
        if sf.empty:
            st.info("No shareholding data in this range.")
        else:
            c1, c2 = st.columns(2)
            with c1:
                fig = go.Figure()
                for col, name, color in [("promoters_pct", "Promoters", BLUE), ("fii_pct", "FII", ORANGE),
                                         ("dii_pct", "DII", AQUA), ("public_pct", "Public", YELLOW)]:
                    fig.add_scatter(x=sf["label"], y=sf[col], name=name, stackgroup="one",
                                    mode="lines", line=dict(color="#fcfcfb", width=2),
                                    fillcolor=color)
                _style(fig, "Shareholding pattern", "% of shares")
                fig.update_yaxes(range=[0, 100])
                _show(fig, "sh_stack")
            with c2:
                _bars(sf, "label", {"num_shareholders": ("Shareholders", BLUE)},
                      "Number of shareholders", "count", "sh_count")

    with t5:
        if p.empty:
            st.info("No peer data yet.")
        else:
            c1, c2 = st.columns(2)
            with c1:
                d = p.sort_values("roce_pct")
                colors = [BLUE if v else MUTED for v in d["is_vintage"]]
                fig = go.Figure(go.Bar(x=d["roce_pct"], y=d["company_name"], orientation="h",
                                       marker_color=colors, name="ROCE %"))
                _style(fig, "ROCE % — Vintage Coffee (blue) vs peers", "", legend=False, height=360)
                fig.update_xaxes(title="ROCE %")
                fig.update_layout(hovermode="closest")
                _show(fig, "peer_roce")
            with c2:
                d = p.dropna(subset=["pe_ratio", "market_cap_cr", "sales_qtr_cr"])
                fig = go.Figure()
                for is_v, name, color in [(0, "Peers", MUTED), (1, "Vintage Coffee", BLUE)]:
                    dd = d[d["is_vintage"] == is_v]
                    fig.add_scatter(x=dd["market_cap_cr"], y=dd["pe_ratio"], mode="markers",
                                    name=name, text=dd["company_name"],
                                    marker=dict(color=color, size=(dd["sales_qtr_cr"] ** 0.5).clip(lower=8),
                                                sizemode="diameter", opacity=0.85,
                                                line=dict(color="#fcfcfb", width=2)),
                                    hovertemplate="<b>%{text}</b><br>Market cap ₹%{x:,.0f} Cr"
                                                  "<br>P/E %{y:.1f}<extra></extra>")
                _style(fig, "Market cap vs P/E (bubble = quarterly sales)", "P/E ratio", height=360)
                fig.update_xaxes(title="Market cap (₹ Cr, log scale)", type="log")
                fig.update_layout(hovermode="closest")
                _show(fig, "peer_bubble")
            with st.expander("Peer table"):
                st.dataframe(p.drop(columns=["peer_id", "company_id", "is_vintage"]), hide_index=True, width="stretch")
