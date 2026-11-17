"""
One-off helper: converts the CA 1 phpMyAdmin dump into sql/data.sql for the
normalised CA 2 schema.  Kept in the repo so the transformation is reproducible.

Usage:  python scripts/make_data_sql.py path/to/phpMyAdmin_dump.sql sql/data.sql
"""
import re
import sys
from pathlib import Path


def parse_inserts(text):
    """Return {table: (columns, [row tuples])} from a phpMyAdmin dump."""
    out = {}
    pat = re.compile(r"INSERT INTO `(\w+)` \((.*?)\) VALUES\s*(.*?);\n", re.S)
    for table, cols, body in pat.findall(text):
        cols = [c.strip(" `") for c in cols.split(",")]
        rows = []
        for line in body.strip().splitlines():
            line = line.strip().rstrip(",")
            rows.append(eval(line.replace("NULL", "None")))  # trusted local file
        out[table] = (cols, rows)
    return out


def lit(v):
    if v is None:
        return "NULL"
    if isinstance(v, str):
        return "'" + v.replace("'", "''") + "'"
    return repr(v)


def emit(table, cols, rows):
    head = f"INSERT INTO {table} ({', '.join(cols)}) VALUES\n"
    body = ",\n".join("(" + ", ".join(lit(v) for v in r) + ")" for r in rows)
    return head + body + ";\n\n"


def main(src, dst):
    data = parse_inserts(Path(src).read_text(encoding="utf-8"))
    sql = ["-- Seed data generated from the CA 1 dump by scripts/make_data_sql.py\n"
           "-- Load AFTER sql/schema.sql\n\n"]

    # ---- reference tables --------------------------------------------------
    cols, rows = data["annual_pnl"]
    ci = {c: i for i, c in enumerate(cols)}
    fy = [(r[ci["year_id"]], r[ci["fiscal_year_end"]], r[ci["year_label"]]) for r in rows]
    sql.append(emit("fiscal_years", ["year_id", "fiscal_year_end", "year_label"], fy))

    q_dates = set()
    for t in ("quarterly_results", "shareholding_pattern"):
        c, r = data[t]
        q_dates |= {x[c.index("quarter_end")] for x in r}
    sql.append(emit("quarters", ["quarter_end"], [(d,) for d in sorted(q_dates)]))

    c, r = data["peer_comparison"]
    comp = [(x[c.index("peer_id")], x[c.index("company_name")],
             1 if x[c.index("company_name")] == "Vintage Coffee" else 0) for x in r]
    sql.append(emit("companies", ["company_id", "company_name", "is_vintage"], comp))

    # ---- annual tables: drop fiscal_year_end / year_label (now in fiscal_years)
    for t in ("annual_pnl", "balance_sheet", "cash_flows", "ratios"):
        c, r = data[t]
        keep = [i for i, n in enumerate(c) if n not in ("fiscal_year_end", "year_label")]
        sql.append(emit(t, [c[i] for i in keep], [tuple(x[i] for i in keep) for x in r]))

    # ---- quarterly tables unchanged ----------------------------------------
    for t in ("quarterly_results", "shareholding_pattern"):
        c, r = data[t]
        sql.append(emit(t, c, r))

    # ---- peer table: company_name -> company_id -----------------------------
    c, r = data["peer_comparison"]
    new_cols = ["peer_id", "company_id"] + [n for n in c if n not in ("peer_id", "company_name")]
    new_rows = []
    for x in r:
        d = dict(zip(c, x))
        new_rows.append(tuple(d["peer_id"] if n == "peer_id" else
                              d["peer_id"] if n == "company_id" else d[n] for n in new_cols))
    sql.append(emit("peer_comparison", new_cols, new_rows))

    Path(dst).write_text("".join(sql), encoding="utf-8")
    print(f"wrote {dst}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
