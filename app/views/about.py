"""About page: project summary, live table sizes and the ER diagram."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from .. import crud
from ..tables import TABLES

ER_PNG = Path(__file__).resolve().parents[2] / "docs" / "er_diagram.png"


def render() -> None:
    st.title("ℹ️ About this project")
    st.markdown(
        """
**Vintage Coffee & Beverages Ltd — Business Management System** (MKT322 Academic Task 2)

CA 1 produced a read-only dashboard from a bundled file. CA 2 turns it into a **live business
management application**: a normalised MySQL database, full **Create / Read / Update / Delete**
screens, validation, and a dashboard that always reflects the current data.

**Stack:** Python · Streamlit · SQLAlchemy + PyMySQL · MySQL · Plotly
        """
    )

    st.subheader("Live table sizes")
    counts = crud.table_counts()
    df = pd.DataFrame([{"table": t.name, "section": t.group, "rows": counts[t.name],
                        "primary key": t.pk} for t in TABLES.values()])
    st.dataframe(df, hide_index=True, width="stretch")

    st.subheader("Entity-relationship diagram")
    if ER_PNG.exists():
        st.image(str(ER_PNG))
    else:
        st.caption("ER diagram image not found (docs/er_diagram.png).")
    st.markdown(
        """
**Relationships**
- `fiscal_years` 1 → 1 `annual_pnl`, `balance_sheet`, `cash_flows`, `ratios` (via `year_id`)
- `quarters` 1 → 1 `quarterly_results`, `shareholding_pattern` (via `quarter_end`)
- `companies` 1 → 1 `peer_comparison` (via `company_id`)
- Foreign keys use `ON DELETE RESTRICT`, so a year / quarter / company that still has data cannot be deleted by mistake.
        """
    )
