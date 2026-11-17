"""
Generic CRUD engine + validation, driven by the declarative config in tables.py.

Every value reaches MySQL as a bound parameter; table/column names come only from
the whitelist in tables.py.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pandas as pd

from . import db
from .tables import TABLES, Field, Table


# ----------------------------------------------------------------------------
# value normalisation
# ----------------------------------------------------------------------------
def clean(v):
    """Turn pandas / numpy / Decimal values into plain Python (None for NaN/NaT)."""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, pd.Timestamp):
        return v.date()
    if isinstance(v, datetime):
        return v.date()
    if hasattr(v, "item") and not isinstance(v, (str, bytes)):
        v = v.item()
    if isinstance(v, Decimal):
        return float(v)
    return v


def _fmt(x: float) -> str:
    return f"{x:,.0f}" if float(x).is_integer() else f"{x:,.2f}"


# ----------------------------------------------------------------------------
# READ
# ----------------------------------------------------------------------------
def list_records(t: Table) -> pd.DataFrame:
    return db.read_df(t.list_sql)


def get_record(t: Table, pk) -> dict | None:
    df = db.read_df(f"SELECT * FROM {t.name} WHERE {t.pk} = :pk", {"pk": pk})
    if df.empty:
        return None
    return {c: clean(df.iloc[0][c]) for c in df.columns}


def fk_options(f: Field, t: Table, exclude_used: bool = False) -> list[tuple]:
    """[(value, label), ...] for a foreign-key dropdown, read live from the parent table."""
    ref_t, ref_c, ref_l = f.ref
    sql = f"SELECT {ref_c} AS value, {ref_l} AS label FROM {ref_t}"
    if exclude_used:
        sql += f" WHERE {ref_c} NOT IN (SELECT {f.name} FROM {t.name})"
    sql += f" ORDER BY {ref_c}"
    df = db.read_df(sql)
    return [(clean(r["value"]), str(clean(r["label"]))) for _, r in df.iterrows()]


def dependents(t: Table, pk) -> list[tuple[str, int]]:
    """How many child rows block deleting this record?  [(nice name, count), ...]"""
    out = []
    for child, col, nice in t.dependents:
        n = int(db.scalar(f"SELECT COUNT(*) FROM {child} WHERE {col} = :pk", {"pk": pk}) or 0)
        if n:
            out.append((nice, n))
    return out


def table_counts() -> dict[str, int]:
    return {name: int(db.scalar(f"SELECT COUNT(*) FROM {name}") or 0) for name in TABLES}


# ----------------------------------------------------------------------------
# VALIDATION
# ----------------------------------------------------------------------------
def validate(t: Table, values: dict, pk=None) -> tuple[dict, list[str], list[str]]:
    """
    Returns (clean_values, errors, warnings).
    `pk` is the record being edited (None when adding) so uniqueness checks skip itself.
    """
    out: dict = {}
    errors: list[str] = []
    warnings: list[str] = []

    for f in t.fields:
        if f.name not in values:
            continue
        v = values[f.name]

        # --- empty values ----------------------------------------------------
        if isinstance(v, str):
            v = v.strip()
            if v == "":
                v = None
        if v is None:
            if f.required:
                errors.append(f"{f.label} is required.")
            out[f.name] = None
            continue

        # --- type / range ----------------------------------------------------
        if f.kind in ("int", "decimal"):
            try:
                num = float(v)
            except (TypeError, ValueError):
                errors.append(f"{f.label} must be a number.")
                continue
            if f.kind == "int":
                if num != int(num):
                    errors.append(f"{f.label} must be a whole number.")
                    continue
                num = int(num)
            else:
                num = round(num, f.scale)
            lo, hi = f.bounds()
            if not (lo <= num <= hi):
                errors.append(f"{f.label} must be between {_fmt(lo)} and {_fmt(hi)}.")
                continue
            out[f.name] = num
        elif f.kind == "text":
            if f.max_len and len(v) > f.max_len:
                errors.append(f"{f.label} can be at most {f.max_len} characters.")
                continue
            out[f.name] = v
        elif f.kind == "date":
            if not isinstance(v, date):
                errors.append(f"{f.label} must be a valid date.")
                continue
            if not (date(1990, 1, 1) <= v <= date(2100, 12, 31)):
                errors.append(f"{f.label} must be between 1990 and 2100.")
                continue
            out[f.name] = v
        elif f.kind == "bool":
            out[f.name] = 1 if v else 0
        else:                                   # fk
            out[f.name] = v

    # --- duplicates (friendlier than the raw MySQL error) -------------------
    for col in t.unique:
        if out.get(col) is None:
            continue
        sql = f"SELECT COUNT(*) FROM {t.name} WHERE {col} = :v"
        params = {"v": out[col]}
        if pk is not None:
            sql += f" AND {t.pk} <> :pk"
            params["pk"] = pk
        if int(db.scalar(sql, params) or 0):
            label = t.field(col).label
            errors.append(f"{label} '{out[col]}' already exists.")

    # --- cross-field business rules ----------------------------------------
    if not errors:
        for rule in t.rules:
            e, w = rule(out)
            errors += e
            warnings += w
    return out, errors, warnings


# ----------------------------------------------------------------------------
# CREATE / UPDATE / DELETE
# ----------------------------------------------------------------------------
def insert(t: Table, values: dict):
    cols = [c for c in values if not (c == t.pk and t.auto_pk)]
    sql = (f"INSERT INTO {t.name} ({', '.join(cols)}) "
           f"VALUES ({', '.join(':' + c for c in cols)})")
    _, last = db.execute(sql, {c: values[c] for c in cols})
    return values[t.pk] if not t.auto_pk else last


def update(t: Table, pk, values: dict) -> int:
    editable = {f.name for f in t.fields if f.editable}
    cols = [c for c in values if c in editable]
    if not cols:
        return 0
    sql = (f"UPDATE {t.name} SET {', '.join(f'{c} = :{c}' for c in cols)} "
           f"WHERE {t.pk} = :__pk")
    params = {c: values[c] for c in cols}
    params["__pk"] = pk
    rows, _ = db.execute(sql, params)
    return rows


def delete(t: Table, pk) -> int:
    rows, _ = db.execute(f"DELETE FROM {t.name} WHERE {t.pk} = :pk", {"pk": pk})
    return rows
