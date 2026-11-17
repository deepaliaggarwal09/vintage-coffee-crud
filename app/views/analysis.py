
"""SQL Analysis page: the CA 1 business questions, run live against MySQL."""
from __future__ import annotations

import re

import streamlit as st

from .. import db

QUERIES = [
    (
        "Quarter-on-quarter sales growth",
        "LAG window function",
        "How fast is revenue growing compared with the previous quarter?",
        """SELECT
    quarter_end,
    sales_cr,
    ROUND(
        (sales_cr - LAG(sales_cr) OVER (ORDER BY quarter_end))
        / NULLIF(LAG(sales_cr) OVER (ORDER BY quarter_end), 0) * 100,
        2
    ) AS qoq_growth_pct
FROM quarterly_results
ORDER BY quarter_end"""
    ),
    (
        "Average operating margin per year",
        "GROUP BY",
        "Is the margin stable as the company scales?",
        """SELECT YEAR(quarter_end) AS calendar_year,
       COUNT(*)                AS quarters,
       ROUND(AVG(opm_pct), 2)  AS avg_opm_pct
FROM quarterly_results
GROUP BY YEAR(quarter_end)
ORDER BY calendar_year"""
    ),
    (
        "Working capital vs cash generation",
        "JOIN (3 tables)",
        "Did shorter working-capital cycles produce more free cash flow?",
        """SELECT f.year_label, r.cash_conversion_cycle, r.working_capital_days, c.free_cash_flow_cr
FROM fiscal_years f
JOIN ratios     r ON r.year_id = f.year_id
JOIN cash_flows c ON c.year_id = f.year_id
ORDER BY f.fiscal_year_end"""
    ),
    (
        "Quarters with above-average sales",
        "Subquery",
        "Which quarters beat the overall average?",
        """SELECT quarter_end, sales_cr
FROM quarterly_results
WHERE sales_cr > (SELECT AVG(sales_cr) FROM quarterly_results)
ORDER BY sales_cr DESC"""
    ),
    (
        "Promoter vs institutional holding",
        "Arithmetic",
        "How is ownership shifting towards institutions?",
        """SELECT quarter_end, promoters_pct, (fii_pct + dii_pct) AS institutional_pct, num_shareholders
FROM shareholding_pattern
ORDER BY quarter_end"""
    ),
    (
        "Peers beating the average ROCE",
        "Subquery + JOIN",
        "Which companies use capital better than the group average?",
        """SELECT c.company_name, p.roce_pct, p.pe_ratio, p.market_cap_cr
FROM peer_comparison p
JOIN companies c ON c.company_id = p.company_id
WHERE p.roce_pct >= (SELECT AVG(roce_pct) FROM peer_comparison)
ORDER BY p.roce_pct DESC"""
    ),
    (
        "Fiscal years missing a balance sheet",
        "LEFT JOIN",
        "Which reporting years have no balance-sheet row yet (e.g. TTM)? Useful as a data-completeness check.",
        """SELECT f.year_label, f.fiscal_year_end
FROM fiscal_years f
LEFT JOIN balance_sheet b ON b.year_id = f.year_id
WHERE b.year_id IS NULL
ORDER BY f.fiscal_year_end"""
    ),
]

_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|replace|call|into|load_file|outfile|dumpfile|sleep|benchmark)\b",
    re.I,
)


def _safe_select(sql: str) -> str | None:
    """Return an error message if the statement is not a single harmless SELECT."""
    s = sql.strip().rstrip(";").strip()
    if not s:
        return "Type a query first."
    if ";" in s:
        return "Only one statement at a time."
    if not re.match(r"(?is)^select\b", s):
        return "Only SELECT queries are allowed here."
    if "--" in s or "/*" in s or "#" in s:
        return "Comments are not allowed."
    m = _FORBIDDEN.search(s)
    if m:
        return f"The keyword '{m.group(0)}' is not allowed in the read-only query box."
    return None


def render() -> None:
    st.title("🧮 SQL analysis")
    st.caption(
        "The business questions from CA 1, executed live against the MySQL database."
    )

    names = [f"{i + 1}. {q[0]}" for i, q in enumerate(QUERIES)]
    pick = st.selectbox("Business question", names)
    title, concept, question, sql = QUERIES[names.index(pick)]

    st.markdown(f"**{question}**  ·  _SQL concept: {concept}_")
    st.code(sql, language="sql")

    try:
        df = db.read_df(sql)
        st.dataframe(df, hide_index=True, width="stretch")
        st.caption(f"{len(df)} row(s)")

        if len(df) and df.select_dtypes("number").shape[1] and df.shape[1] >= 2:
            x = df.columns[0]
            ycols = [
                c for c in df.select_dtypes("number").columns if c != x
            ]
            if ycols:
                st.bar_chart(df.set_index(x)[ycols[0]])

    except Exception as exc:  # noqa: BLE001
        st.error(db.friendly_error(exc))

    st.divider()
    st.subheader("Try your own query")
    st.caption(
        "Read-only: a single SELECT statement. Tables: fiscal_years, quarters, "
        "companies, annual_pnl, balance_sheet, cash_flows, ratios, "
        "quarterly_results, shareholding_pattern, peer_comparison."
    )

    custom = st.text_area(
        "SQL",
        value="SELECT * FROM quarterly_results ORDER BY quarter_end DESC LIMIT 5",
        height=110,
        key="custom_sql",
    )

    if st.button("▶ Run query", type="primary"):
        err = _safe_select(custom)

        if err:
            st.error(err, icon="🚫")
        else:
            try:
                out = db.read_df(custom.strip().rstrip(";"))
                st.dataframe(out.head(1000), hide_index=True, width="stretch")
                st.caption(
                    f"{len(out)} row(s)"
                    + (" (showing first 1000)" if len(out) > 1000 else "")
                )
            except Exception as exc:  # noqa: BLE001
                st.error(db.friendly_error(exc))
