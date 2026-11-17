"""Manage Records page: View / Add / Update / Delete for every table."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from .. import crud, db
from ..tables import TABLES, Field, Table


# ----------------------------------------------------------------------------
# small helpers
# ----------------------------------------------------------------------------
def _ver(t: Table) -> int:
    return st.session_state.setdefault(f"ver_{t.name}", 0)


def _bump(t: Table) -> None:
    st.session_state[f"ver_{t.name}"] = _ver(t) + 1


def _flash(kind: str, msg: str) -> None:
    st.session_state["flash"] = (kind, msg)


def _show_flash() -> None:
    if "flash" in st.session_state:
        kind, msg = st.session_state.pop("flash")
        getattr(st, kind)(msg, icon="✅" if kind == "success" else None)


def _label(f: Field) -> str:
    return f.label + (" *" if f.required else "")


def _widget(f: Field, t: Table, key: str, default=None, mode: str = "add"):
    """Render one input widget for a field and return its value."""
    help_ = f.help
    if f.kind == "decimal":
        lo, hi = f.bounds()
        step = 10 ** (-f.scale)
        return st.number_input(_label(f), min_value=float(lo), max_value=float(hi),
                               value=None if default is None else float(default),
                               step=float(step), format=f"%.{f.scale}f", key=key, help=help_)
    if f.kind == "int":
        lo, hi = f.bounds()
        return st.number_input(_label(f), min_value=int(lo), max_value=int(hi),
                               value=None if default is None else int(default),
                               step=1, format="%d", key=key, help=help_)
    if f.kind == "date":
        return st.date_input(_label(f), value=default or date.today(),
                             min_value=date(1990, 1, 1), max_value=date(2100, 12, 31),
                             key=key, help=help_)
    if f.kind == "bool":
        return st.checkbox(f.label, value=bool(default), key=key, help=help_)
    if f.kind == "fk":
        opts = crud.fk_options(f, t, exclude_used=(mode == "add" and f.unique_fk))
        if mode == "update" and not f.editable:
            st.text_input(_label(f), value=dict(opts).get(default) or dict(crud.fk_options(f, t)).get(default, str(default)),
                          disabled=True, key=key + "_ro", help=help_)
            return default
        if mode == "add" and not opts:
            st.warning(f"No free {f.ref[0].replace('_', ' ')} left. Add one first under "
                       f"Reference data → {f.ref[0].replace('_', ' ').title()}.")
            return None
        values = [v for v, _ in opts]
        labels = dict(opts)
        idx = values.index(default) if default in values else None
        return st.selectbox(_label(f), values, index=idx, format_func=lambda v: labels.get(v, str(v)),
                            placeholder="Select…", key=key, help=help_)
    # text
    return st.text_input(_label(f), value=default or "", max_chars=f.max_len, key=key, help=help_)


def _form_fields(t: Table, mode: str, record: dict | None, key_prefix: str) -> dict:
    """Lay the widgets out in 3 columns and return {field: value}."""
    values: dict = {}
    cols = st.columns(3)
    for i, f in enumerate(t.fields):
        with cols[i % 3]:
            default = record.get(f.name) if record else f.default
            values[f.name] = _widget(f, t, f"{key_prefix}_{f.name}", default, mode)
    return values


def _report_problems(errors: list[str], warnings: list[str] | None = None) -> None:
    for e in errors:
        st.error(e, icon="🚫")
    for w in warnings or []:
        st.warning(w, icon="⚠️")


def _record_picker(t: Table, df: pd.DataFrame, key: str):
    """Select box listing every record of the table; returns the chosen primary key."""
    pks = [crud.clean(x) for x in df[t.pk].tolist()]
    labels = {pk: f"{crud.clean(row[t.label_col])}  ·  {t.pk} {pk}" if t.label_col != t.pk
              else str(pk) for pk, (_, row) in zip(pks, df.iterrows())}
    return st.selectbox("Choose the record", pks, format_func=lambda p: labels[p], key=key,
                        index=None, placeholder="Select a record…")


# ----------------------------------------------------------------------------
# the four operations
# ----------------------------------------------------------------------------
def _tab_view(t: Table) -> None:
    df = crud.list_records(t)
    c1, c2 = st.columns([2, 2])
    q = c1.text_input("🔎 Search", placeholder="Type to filter any column…", key=f"q_{t.name}")
    if t.date_filter_col and not df.empty:
        dates = pd.to_datetime(df[t.date_filter_col])
        lo, hi = dates.min().date(), dates.max().date()
        rng = c2.date_input("📆 Date range", value=(lo, hi), min_value=lo, max_value=hi,
                            key=f"rng_{t.name}")
        if isinstance(rng, tuple) and len(rng) == 2:
            df = df[(dates >= pd.Timestamp(rng[0])) & (dates <= pd.Timestamp(rng[1]))]
    if q:
        mask = df.astype(str).apply(lambda col: col.str.contains(q, case=False, na=False)).any(axis=1)
        df = df[mask]
    m1, m2 = st.columns([3, 1])
    m1.caption(f"{len(df)} record(s) · live from MySQL table `{t.name}`")
    m2.download_button("⬇️ CSV", df.to_csv(index=False).encode("utf-8"),
                       file_name=f"{t.name}.csv", mime="text/csv", key=f"dl_{t.name}")
    if df.empty:
        st.info("No records match.")
    else:
        st.dataframe(df, hide_index=True, width="stretch")


def _tab_add(t: Table) -> None:
    st.markdown(f"**Add a new record to {t.label.lower()}.** Fields marked * are required.")
    with st.form(f"add_{t.name}_{_ver(t)}"):
        values = _form_fields(t, "add", None, f"add_{t.name}_{_ver(t)}")
        submitted = st.form_submit_button("➕ Add record", type="primary")
    if not submitted:
        return
    clean_vals, errors, warnings = crud.validate(t, values)
    if errors:
        _report_problems(errors, warnings)
        return
    try:
        new_pk = crud.insert(t, clean_vals)
    except Exception as exc:  # noqa: BLE001
        st.error(db.friendly_error(exc), icon="🚫")
        return
    msg = (f"Added to {t.label.lower()} (id {new_pk})." if t.auto_pk
           else f"Added to {t.label.lower()}: {new_pk}.")
    if warnings:
        msg += "  Note: " + " ".join(warnings)
    _flash("success", msg)
    _bump(t)
    st.rerun()


def _tab_update(t: Table) -> None:
    df = crud.list_records(t)
    if df.empty:
        st.info("Nothing to update yet.")
        return
    pk = _record_picker(t, df, f"upd_pick_{t.name}")
    if pk is None:
        st.caption("Pick a record to edit.")
        return
    record = crud.get_record(t, pk)
    if record is None:
        st.error("That record no longer exists (someone may have deleted it). Reload the list.")
        return
    prefix = f"upd_{t.name}_{pk}_{_ver(t)}"
    with st.form(prefix):
        values = _form_fields(t, "update", record, prefix)
        submitted = st.form_submit_button("💾 Save changes", type="primary")
    if not submitted:
        return
    clean_vals, errors, warnings = crud.validate(t, values, pk=pk)
    if errors:
        _report_problems(errors, warnings)
        return
    try:
        crud.update(t, pk, clean_vals)
    except Exception as exc:  # noqa: BLE001
        st.error(db.friendly_error(exc), icon="🚫")
        return
    msg = f"Record {pk} updated."
    if warnings:
        msg += "  Note: " + " ".join(warnings)
    _flash("success", msg)
    _bump(t)
    st.rerun()


def _tab_delete(t: Table) -> None:
    df = crud.list_records(t)
    if df.empty:
        st.info("Nothing to delete.")
        return
    pk = _record_picker(t, df, f"del_pick_{t.name}")
    if pk is None:
        st.caption("Pick the record you want to remove.")
        return
    record = crud.get_record(t, pk)
    if record is None:
        st.error("That record no longer exists. Reload the list.")
        return
    st.dataframe(pd.DataFrame({"column": list(record.keys()),
                               "value": [str(v) if v is not None else "—" for v in record.values()]}),
                 hide_index=True, width="stretch")
    blockers = crud.dependents(t, pk)
    if blockers:
        st.error("Cannot delete: this record is still used by "
                 + ", ".join(f"{n} row(s) in {name}" for name, n in blockers)
                 + ". Remove those first (foreign-key protection).", icon="🔒")
        return
    confirm = st.checkbox("I understand this permanently deletes the record.", key=f"del_ok_{t.name}_{pk}")
    if st.button("🗑️ Delete record", type="primary", disabled=not confirm, key=f"del_btn_{t.name}"):
        try:
            rows = crud.delete(t, pk)
        except Exception as exc:  # noqa: BLE001
            st.error(db.friendly_error(exc), icon="🚫")
            return
        if rows:
            _flash("success", f"Record {pk} deleted from {t.label.lower()}.")
        else:
            _flash("warning", "Nothing was deleted — the record was already gone.")
        _bump(t)
        st.session_state.pop(f"del_pick_{t.name}", None)
        st.rerun()


# ----------------------------------------------------------------------------
# page entry point
# ----------------------------------------------------------------------------
def render() -> None:
    st.title("🗂️ Manage records")
    st.caption("Add, view, update and delete rows in any MySQL table. Every change is saved to the database immediately.")
    _show_flash()

    groups: dict[str, list[Table]] = {}
    for t in TABLES.values():
        groups.setdefault(t.group, []).append(t)

    c1, c2 = st.columns([1, 2])
    group = c1.selectbox("Section", list(groups), key="mg_group")
    tbl = c2.selectbox("Table", [t.name for t in groups[group]],
                       format_func=lambda n: f"{TABLES[n].icon} {TABLES[n].label}", key=f"mg_tbl_{group}")
    t = TABLES[tbl]
    st.info(t.description, icon="ℹ️")

    op = st.radio("Operation", ["👁️ View", "➕ Add", "✏️ Update", "🗑️ Delete"],
                  horizontal=True, key="mg_op")
    st.divider()
    if op.endswith("View"):
        _tab_view(t)
    elif op.endswith("Add"):
        _tab_add(t)
    elif op.endswith("Update"):
        _tab_update(t)
    else:
        _tab_delete(t)
