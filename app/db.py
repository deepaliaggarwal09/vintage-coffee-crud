
"""
Database layer: connection handling, query helpers and friendly error messages.

Credentials are looked up in this order:
  1. Streamlit secrets -> [mysql] section
  2. Environment variables -> DB_HOST, DB_PORT, DB_USER, DB_PASSWORD,
                               DB_NAME, DB_SSL, DB_SSL_CA
  3. .streamlit/secrets.toml read directly

An empty password is allowed for local MySQL accounts that use no password.
No password is stored in this source code.
"""
from __future__ import annotations

import os
import ssl
import threading
import tomllib
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine

ROOT = Path(__file__).resolve().parent.parent
_lock = threading.Lock()
_engine: Engine | None = None


class DBConfigError(RuntimeError):
    """Raised when usable database configuration is missing."""


# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------
def _truthy(v) -> bool:
    return str(v).strip().lower() in {"1", "true", "yes", "y", "on"}


def load_config() -> dict:
    cfg: dict = {}

    # 1) Streamlit secrets
    try:
        import streamlit as st

        if "mysql" in st.secrets:
            cfg = dict(st.secrets["mysql"])
    except Exception:
        pass

    # 2) Read secrets.toml directly for scripts
    if not cfg:
        f = ROOT / ".streamlit" / "secrets.toml"
        if f.exists():
            cfg = dict(
                tomllib.loads(f.read_text(encoding="utf-8")).get("mysql", {})
            )

    # 3) Environment variables override settings when provided.
    # An explicitly empty DB_PASSWORD is allowed.
    env_map = {
        "host": "DB_HOST",
        "port": "DB_PORT",
        "user": "DB_USER",
        "password": "DB_PASSWORD",
        "database": "DB_NAME",
        "ssl": "DB_SSL",
        "ssl_ca": "DB_SSL_CA",
    }

    for key, env in env_map.items():
        if env in os.environ:
            cfg[key] = os.environ[env]

    # Password must be configured, but may legitimately be empty.
    missing = [
        key for key in ("host", "user", "database")
        if not str(cfg.get(key, "")).strip()
    ]

    if "password" not in cfg or cfg["password"] is None:
        missing.append("password")

    if missing:
        raise DBConfigError(
            "Database configuration is missing: "
            + ", ".join(missing)
            + ". Check .streamlit/secrets.toml or DB_* environment variables."
        )

    cfg.setdefault("port", 3306)
    return cfg


def _ssl_context(cfg: dict):
    """Create an SSL context for MySQL providers that require TLS."""
    if not _truthy(cfg.get("ssl", False)):
        return None

    ca = cfg.get("ssl_ca")

    if ca:
        ctx = ssl.create_default_context()

        if "BEGIN CERTIFICATE" in str(ca):
            ctx.load_verify_locations(cadata=str(ca))
        else:
            ctx.load_verify_locations(cafile=str(ca))

        return ctx

    # Compatibility option for providers without a supplied CA certificate.
    # Prefer a CA certificate for verified TLS whenever possible.
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


# ----------------------------------------------------------------------------
# Engine and query helpers
# ----------------------------------------------------------------------------
def get_engine() -> Engine:
    """Create and reuse the SQLAlchemy engine."""
    global _engine

    with _lock:
        if _engine is None:
            cfg = load_config()

            url = URL.create(
                "mysql+pymysql",
                username=str(cfg["user"]),
                password=str(cfg["password"]),
                host=str(cfg["host"]),
                port=int(cfg["port"]),
                database=str(cfg["database"]),
                query={"charset": "utf8mb4"},
            )

            connect_args = {"connect_timeout": 15}
            ctx = _ssl_context(cfg)

            if ctx is not None:
                connect_args["ssl"] = ctx

            _engine = create_engine(
                url,
                connect_args=connect_args,
                pool_pre_ping=True,
                pool_recycle=280,
                pool_size=5,
                max_overflow=5,
            )

        return _engine


def reset_engine() -> None:
    """Dispose of the current engine and recreate it on the next request."""
    global _engine

    with _lock:
        if _engine is not None:
            _engine.dispose()
        _engine = None


def check_connection() -> None:
    """Verify that MySQL accepts a connection and a simple query."""
    with get_engine().connect() as conn:
        conn.execute(text("SELECT 1"))


def read_df(sql: str, params: dict | None = None) -> pd.DataFrame:
    """Run a SELECT query and return its results as a DataFrame."""
    with get_engine().connect() as conn:
        return pd.read_sql(text(sql), conn, params=params or {})


def execute(sql: str, params: dict | None = None) -> tuple[int, int | None]:
    """Execute INSERT, UPDATE, or DELETE in a transaction."""
    with get_engine().begin() as conn:
        res = conn.execute(text(sql), params or {})
        last = getattr(res, "lastrowid", None)
        return res.rowcount, (last or None)


def scalar(sql: str, params: dict | None = None):
    """Execute a query and return its first scalar result."""
    with get_engine().connect() as conn:
        return conn.execute(text(sql), params or {}).scalar()


# ----------------------------------------------------------------------------
# Friendly database error messages
# ----------------------------------------------------------------------------
def friendly_error(exc: Exception) -> str:
    orig = getattr(exc, "orig", exc)

    code = (
        orig.args[0]
        if getattr(orig, "args", None)
        and isinstance(orig.args[0], int)
        else None
    )

    raw = (
        str(orig.args[1])
        if getattr(orig, "args", None) and len(orig.args) > 1
        else str(orig)
    )

    if code == 1062:
        return "Duplicate entry: a record with the same unique value already exists."

    if code == 1451:
        return (
            "This record is still referenced by other records (foreign key). "
            "Delete or move the dependent records first."
        )

    if code == 1452:
        return "The selected parent record (year / quarter / company) does not exist."

    if code == 1048:
        return "A required (NOT NULL) value was left empty."

    if code in (1264, 1366, 1292):
        return "A value is out of range or has the wrong type for its column."

    if code == 1406:
        return "A text value is too long for its column."

    if code in (3819, 4025):
        return "A database CHECK rule was violated (e.g. a percentage outside 0-100)."

    if code in (2002, 2003, 2006, 2013):
        return (
            "Cannot reach the MySQL server. Check host, port, firewall, "
            "and that the database server is running."
        )

    if code == 1045:
        return "MySQL rejected the username or password."

    if code == 1049:
        return "The configured database name does not exist on the server."

    return f"Database error: {raw}"
