"""
Declarative description of every table: columns, types, limits, foreign keys,
cross-field business rules and which child tables depend on it.

The CRUD pages are generated from this file, so adding a column or a table here
automatically gives it forms, validation and delete-protection.  Table and column
names below are the ONLY identifiers ever placed into SQL text (everything the
user types is passed as bound parameters) -> no SQL injection.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable

QUARTER_ENDS = {(3, 31), (6, 30), (9, 30), (12, 31)}


@dataclass
class Field:
    name: str
    label: str
    kind: str                      # int | decimal | date | text | fk | bool
    required: bool = False
    precision: int = 10            # decimal(p, s)
    scale: int = 2
    min: float | None = None
    max: float | None = None
    max_len: int | None = None
    help: str | None = None
    # foreign key info: (ref_table, ref_column, label_column)
    ref: tuple[str, str, str] | None = None
    unique_fk: bool = False        # on ADD only offer parents that have no row here yet
    editable: bool = True          # editable on UPDATE?
    default: object = None

    def bounds(self) -> tuple[float, float]:
        """Numeric limits implied by the column type unless overridden."""
        if self.kind == "int":
            lo, hi = -2_147_483_648, 2_147_483_647
        else:
            hi = 10 ** (self.precision - self.scale) - 10 ** (-self.scale)
            lo = -hi
        return (self.min if self.min is not None else lo,
                self.max if self.max is not None else hi)


Rule = Callable[[dict], tuple[list, list]]   # values -> (errors, warnings)


@dataclass
class Table:
    name: str
    label: str
    icon: str
    group: str
    pk: str
    auto_pk: bool
    fields: list[Field]
    list_sql: str                  # what the View tab shows (joined with labels)
    label_col: str                 # column of list_sql used to name a record in pick-lists
    description: str = ""
    rules: list[Rule] = field(default_factory=list)
    # child tables that block deletion: (child_table, child_column, nice name)
    dependents: list[tuple[str, str, str]] = field(default_factory=list)
    date_filter_col: str | None = None
    unique: list[str] = field(default_factory=list)   # columns pre-checked for duplicates

    def field(self, name: str) -> Field:
        return next(f for f in self.fields if f.name == name)


# ----------------------------------------------------------------------------
# business rules (cross-field validation)
# ----------------------------------------------------------------------------
def _has(v, *keys):
    return all(v.get(k) is not None for k in keys)


def rule_pnl(v: dict):
    err, warn = [], []
    if _has(v, "sales_cr", "expenses_cr", "operating_profit_cr"):
        diff = v["sales_cr"] - v["expenses_cr"] - v["operating_profit_cr"]
        if abs(diff) > 2:
            err.append("Operating profit should be about Sales - Expenses "
                       f"(difference is {diff:+.2f} Cr; rounding tolerance is 2 Cr).")
    if _has(v, "sales_cr", "operating_profit_cr", "opm_pct") and v["sales_cr"]:
        calc = v["operating_profit_cr"] / v["sales_cr"] * 100
        if abs(calc - v["opm_pct"]) > 3:
            warn.append(f"OPM % looks inconsistent: Operating profit / Sales = {calc:.1f}%, you entered {v['opm_pct']:.1f}%.")
    if _has(v, "sales_cr") and v["sales_cr"] < 0:
        err.append("Sales cannot be negative.")
    return err, warn


def rule_balance_sheet(v: dict):
    err = []
    if _has(v, "equity_capital_cr", "reserves_cr", "borrowings_cr", "other_liabilities_cr", "total_liabilities_cr"):
        s = v["equity_capital_cr"] + v["reserves_cr"] + v["borrowings_cr"] + v["other_liabilities_cr"]
        if abs(s - v["total_liabilities_cr"]) > 2:
            err.append(f"Total liabilities should equal capital + reserves + borrowings + other (= {s:.2f}).")
    if _has(v, "fixed_assets_cr", "cwip_cr", "investments_cr", "other_assets_cr", "total_assets_cr"):
        s = v["fixed_assets_cr"] + v["cwip_cr"] + v["investments_cr"] + v["other_assets_cr"]
        if abs(s - v["total_assets_cr"]) > 2:
            err.append(f"Total assets should equal fixed + CWIP + investments + other (= {s:.2f}).")
    if _has(v, "total_liabilities_cr", "total_assets_cr"):
        if abs(v["total_liabilities_cr"] - v["total_assets_cr"]) > 2:
            err.append("The balance sheet does not balance: total liabilities must equal total assets.")
    return err, []


def rule_cash_flow(v: dict):
    if _has(v, "cfo_cr", "cfi_cr", "cff_cr", "net_cash_flow_cr"):
        s = v["cfo_cr"] + v["cfi_cr"] + v["cff_cr"]
        if abs(s - v["net_cash_flow_cr"]) > 2:
            return [f"Net cash flow should equal CFO + CFI + CFF (= {s:.2f})."], []
    return [], []


def rule_ratios(v: dict):
    if _has(v, "debtor_days", "inventory_days", "days_payable", "cash_conversion_cycle"):
        s = v["debtor_days"] + v["inventory_days"] - v["days_payable"]
        if abs(s - v["cash_conversion_cycle"]) > 2:
            return [f"Cash conversion cycle should equal debtor days + inventory days - days payable (= {s})."], []
    return [], []


def rule_shareholding(v: dict):
    keys = ("promoters_pct", "fii_pct", "dii_pct", "public_pct")
    if _has(v, *keys):
        s = sum(v[k] for k in keys)
        if abs(s - 100) > 0.5:
            return [f"Promoter + FII + DII + Public must add up to 100% (currently {s:.2f}%)."], []
    return [], []


def rule_quarter_end(v: dict):
    d = v.get("quarter_end")
    if isinstance(d, date) and (d.month, d.day) not in QUARTER_ENDS:
        return ["Quarter end must be 31-Mar, 30-Jun, 30-Sep or 31-Dec."], []
    return [], []


def rule_fiscal_year(v: dict):
    lab = (v.get("year_label") or "").strip()
    if lab and len(lab) > 10:
        return ["Year label can be at most 10 characters."], []
    return [], []


def rule_company(v: dict):
    n = (v.get("company_name") or "").strip()
    if n and not any(ch.isalpha() for ch in n):
        return ["Company name must contain letters."], []
    return [], []


# ----------------------------------------------------------------------------
# field helpers
# ----------------------------------------------------------------------------
def D(name, label, p=10, s=2, **kw):
    return Field(name, label, "decimal", precision=p, scale=s, **kw)


def I(name, label, **kw):
    return Field(name, label, "int", **kw)


YEAR_FK = ("fiscal_years", "year_id", "year_label")
QUARTER_FK = ("quarters", "quarter_end", "quarter_end")
COMPANY_FK = ("companies", "company_id", "company_name")


def _year_field():
    return Field("year_id", "Fiscal year", "fk", required=True, ref=YEAR_FK,
                 unique_fk=True, editable=False, help="One row per fiscal year.")


def _quarter_field():
    return Field("quarter_end", "Quarter end", "fk", required=True, ref=QUARTER_FK,
                 unique_fk=True, help="Add the quarter under 'Quarters' first if it is not listed.")


def _pnl_fields():
    return [
        D("sales_cr", "Sales (₹ Cr)"),
        D("expenses_cr", "Expenses (₹ Cr)"),
        D("operating_profit_cr", "Operating profit (₹ Cr)"),
        D("opm_pct", "OPM %", p=5, s=2, min=-1000, max=1000),
        D("other_income_cr", "Other income (₹ Cr)"),
        D("interest_cr", "Interest (₹ Cr)"),
        D("depreciation_cr", "Depreciation (₹ Cr)"),
        D("profit_before_tax_cr", "Profit before tax (₹ Cr)"),
        D("tax_pct", "Tax %", p=5, s=2, min=-100, max=200),
        D("net_profit_cr", "Net profit (₹ Cr)"),
        D("eps_rs", "EPS (₹)", p=6, s=2),
    ]


# ----------------------------------------------------------------------------
# the tables
# ----------------------------------------------------------------------------
TABLES: dict[str, Table] = {}


def _add(t: Table):
    TABLES[t.name] = t


_add(Table(
    name="fiscal_years", label="Fiscal years", icon="📅", group="Reference data",
    pk="year_id", auto_pk=True,
    description="Reporting years used by the annual tables (FY Mar-22 … FY Mar-26 and TTM).",
    fields=[
        Field("fiscal_year_end", "Fiscal year end", "date", required=True),
        Field("year_label", "Label", "text", required=True, max_len=10, help="e.g. 'Mar 2027' (max 10 chars)"),
    ],
    list_sql="SELECT year_id, fiscal_year_end, year_label FROM fiscal_years ORDER BY fiscal_year_end",
    label_col="year_label", rules=[rule_fiscal_year], date_filter_col="fiscal_year_end",
    unique=["fiscal_year_end", "year_label"],
    dependents=[("annual_pnl", "year_id", "Annual P&L"), ("balance_sheet", "year_id", "Balance sheet"),
                ("cash_flows", "year_id", "Cash flows"), ("ratios", "year_id", "Ratios")],
))

_add(Table(
    name="quarters", label="Quarters", icon="🗓️", group="Reference data",
    pk="quarter_end", auto_pk=False,
    description="Quarter-end dates shared by quarterly results and shareholding.",
    fields=[Field("quarter_end", "Quarter end", "date", required=True,
                  help="31-Mar, 30-Jun, 30-Sep or 31-Dec. Editing a date cascades to its results.")],
    list_sql="SELECT quarter_end FROM quarters ORDER BY quarter_end",
    label_col="quarter_end", rules=[rule_quarter_end], date_filter_col="quarter_end",
    unique=["quarter_end"],
    dependents=[("quarterly_results", "quarter_end", "Quarterly results"),
                ("shareholding_pattern", "quarter_end", "Shareholding pattern")],
))

_add(Table(
    name="companies", label="Companies", icon="🏢", group="Reference data",
    pk="company_id", auto_pk=True,
    description="Vintage Coffee and the listed peers used for benchmarking.",
    fields=[
        Field("company_name", "Company name", "text", required=True, max_len=50),
        Field("is_vintage", "This is Vintage Coffee", "bool", default=False),
    ],
    list_sql="SELECT company_id, company_name, is_vintage FROM companies ORDER BY company_id",
    label_col="company_name", rules=[rule_company], unique=["company_name"],
    dependents=[("peer_comparison", "company_id", "Peer comparison")],
))

_add(Table(
    name="quarterly_results", label="Quarterly results", icon="📈", group="Financials",
    pk="quarter_id", auto_pk=True,
    description="Quarterly P&L: sales, margins, profit and EPS.",
    fields=[_quarter_field()] + _pnl_fields(),
    list_sql="SELECT * FROM quarterly_results ORDER BY quarter_end",
    label_col="quarter_end", rules=[rule_pnl, rule_quarter_end], date_filter_col="quarter_end",
))

_add(Table(
    name="annual_pnl", label="Annual P&L", icon="📊", group="Financials",
    pk="year_id", auto_pk=False,
    description="Yearly profit & loss account.",
    fields=[_year_field()] + _pnl_fields() + [
        D("dividend_payout_pct", "Dividend payout %", p=6, s=2, min=0, max=100),
    ],
    list_sql=("SELECT f.year_label AS period, f.fiscal_year_end, a.* FROM annual_pnl a "
              "JOIN fiscal_years f ON f.year_id = a.year_id ORDER BY f.fiscal_year_end"),
    label_col="period", rules=[rule_pnl], date_filter_col="fiscal_year_end",
))

_add(Table(
    name="balance_sheet", label="Balance sheet", icon="🏦", group="Financials",
    pk="year_id", auto_pk=False,
    description="Year-end liabilities and assets.",
    fields=[_year_field(),
            D("equity_capital_cr", "Equity capital (₹ Cr)"), D("reserves_cr", "Reserves (₹ Cr)"),
            D("borrowings_cr", "Borrowings (₹ Cr)"), D("other_liabilities_cr", "Other liabilities (₹ Cr)"),
            D("total_liabilities_cr", "Total liabilities (₹ Cr)"),
            D("fixed_assets_cr", "Fixed assets (₹ Cr)"), D("cwip_cr", "CWIP (₹ Cr)"),
            D("investments_cr", "Investments (₹ Cr)"), D("other_assets_cr", "Other assets (₹ Cr)"),
            D("total_assets_cr", "Total assets (₹ Cr)")],
    list_sql=("SELECT f.year_label AS period, f.fiscal_year_end, b.* FROM balance_sheet b "
              "JOIN fiscal_years f ON f.year_id = b.year_id ORDER BY f.fiscal_year_end"),
    label_col="period", rules=[rule_balance_sheet], date_filter_col="fiscal_year_end",
))

_add(Table(
    name="cash_flows", label="Cash flows", icon="💵", group="Financials",
    pk="year_id", auto_pk=False,
    description="Operating, investing and financing cash flows.",
    fields=[_year_field(),
            D("cfo_cr", "Cash from operations (₹ Cr)"), D("cfi_cr", "Cash from investing (₹ Cr)"),
            D("cff_cr", "Cash from financing (₹ Cr)"), D("net_cash_flow_cr", "Net cash flow (₹ Cr)"),
            D("free_cash_flow_cr", "Free cash flow (₹ Cr)"),
            D("cfo_op_pct", "CFO / Operating profit %", p=8, s=2, min=-100000, max=100000)],
    list_sql=("SELECT f.year_label AS period, f.fiscal_year_end, c.* FROM cash_flows c "
              "JOIN fiscal_years f ON f.year_id = c.year_id ORDER BY f.fiscal_year_end"),
    label_col="period", rules=[rule_cash_flow], date_filter_col="fiscal_year_end",
))

_add(Table(
    name="ratios", label="Efficiency ratios", icon="⚙️", group="Financials",
    pk="year_id", auto_pk=False,
    description="Working-capital days and ROCE.",
    fields=[_year_field(),
            I("debtor_days", "Debtor days", min=0, max=5000), I("inventory_days", "Inventory days", min=0, max=5000),
            I("days_payable", "Days payable", min=0, max=5000),
            I("cash_conversion_cycle", "Cash conversion cycle (days)", min=-5000, max=10000),
            I("working_capital_days", "Working capital days", min=-5000, max=10000),
            D("roce_pct", "ROCE %", p=5, s=2, min=-100, max=100)],
    list_sql=("SELECT f.year_label AS period, f.fiscal_year_end, r.* FROM ratios r "
              "JOIN fiscal_years f ON f.year_id = r.year_id ORDER BY f.fiscal_year_end"),
    label_col="period", rules=[rule_ratios], date_filter_col="fiscal_year_end",
))

_add(Table(
    name="shareholding_pattern", label="Shareholding pattern", icon="👥", group="Ownership & peers",
    pk="quarter_id", auto_pk=True,
    description="Who owns the company each quarter.",
    fields=[_quarter_field(),
            D("promoters_pct", "Promoters %", p=5, s=2, min=0, max=100),
            D("fii_pct", "FII %", p=5, s=2, min=0, max=100),
            D("dii_pct", "DII %", p=5, s=2, min=0, max=100),
            D("public_pct", "Public %", p=5, s=2, min=0, max=100),
            I("num_shareholders", "Number of shareholders", min=0, max=1_000_000_000)],
    list_sql="SELECT * FROM shareholding_pattern ORDER BY quarter_end",
    label_col="quarter_end", rules=[rule_shareholding, rule_quarter_end], date_filter_col="quarter_end",
))

_add(Table(
    name="peer_comparison", label="Peer comparison", icon="🏆", group="Ownership & peers",
    pk="peer_id", auto_pk=True,
    description="Valuation and performance of Vintage Coffee against listed peers.",
    fields=[Field("company_id", "Company", "fk", required=True, ref=COMPANY_FK, unique_fk=True,
                  help="Add the company under 'Companies' first if it is not listed."),
            D("cmp_rs", "Current market price (₹)", min=0), D("pe_ratio", "P/E ratio", p=6, s=2, min=0),
            D("market_cap_cr", "Market cap (₹ Cr)", p=12, s=2, min=0),
            D("div_yield_pct", "Dividend yield %", p=5, s=2, min=0, max=100),
            D("net_profit_qtr_cr", "Net profit - quarter (₹ Cr)"),
            D("qtr_profit_var_pct", "Quarter profit variation %", p=8, s=2, min=-100000, max=100000),
            D("sales_qtr_cr", "Sales - quarter (₹ Cr)", min=0),
            D("qtr_sales_var_pct", "Quarter sales variation %", p=8, s=2, min=-100000, max=100000),
            D("roce_pct", "ROCE %", p=6, s=2, min=-100, max=100)],
    list_sql=("SELECT c.company_name, p.* FROM peer_comparison p "
              "JOIN companies c ON c.company_id = p.company_id ORDER BY p.roce_pct DESC"),
    label_col="company_name",
))
