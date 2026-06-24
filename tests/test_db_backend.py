"""Tests for db_backend — SQL translation + backend factory."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import warnings
warnings.filterwarnings("ignore")
import logging
logging.disable(logging.CRITICAL)

from core.db_backend import (
    _translate_to_pg,
    _PGConnection,
    _SQLiteConnection,
    create_backend,
    _parse_url,
    _detect_backend,
)


# ── _translate_to_pg (standalone) ──────────────────────────────

def test_translate_simple():
    assert _translate_to_pg("SELECT * FROM t WHERE id = ?") == "SELECT * FROM t WHERE id = $1"


def test_translate_multiple():
    sql = "INSERT INTO t (a, b) VALUES (?, ?)"
    assert _translate_to_pg(sql) == "INSERT INTO t (a, b) VALUES ($1, $2)"


def test_translate_no_placeholder():
    assert _translate_to_pg("SELECT 1") == "SELECT 1"


def test_translate_question_mark_in_string():
    sql = "SELECT * FROM t WHERE name = 'hello?'"
    assert "?" in _translate_to_pg(sql)


def test_translate_mixed():
    sql = "SELECT ? WHERE a = '?' AND b = ?"
    assert _translate_to_pg(sql) == "SELECT $1 WHERE a = '?' AND b = $2"


# ── _PGConnection._translate ───────────────────────────────────

def test_pg_translate_datetime_now():
    sql = "INSERT INTO t (ts) VALUES (datetime('now'))"
    result = _PGConnection._translate(sql)
    assert "NOW()" in result
    assert "datetime" not in result


def test_pg_translate_combined():
    sql = "SELECT ? WHERE ts = datetime('now')"
    result = _PGConnection._translate(sql)
    assert "$1" in result
    assert "NOW()" in result


def test_pg_translate_identity():
    sql = "SELECT 1"
    assert _PGConnection._translate(sql) == "SELECT 1"


# ── _SQLiteConnection._translate (identity) ────────────────────

def test_sqlite_translate_passthrough():
    sql = "SELECT ? WHERE ts = datetime('now')"
    assert _SQLiteConnection._translate(sql) == sql


# ── _parse_url ─────────────────────────────────────────────────

def test_parse_url_pg():
    scheme, cfg = _parse_url("postgresql://user:pass@localhost/db")
    assert scheme == "postgresql"
    assert "url" in cfg
    assert "user" in cfg["url"]


def test_parse_url_sqlite():
    scheme, cfg = _parse_url("sqlite:///emo_ai.db")
    assert scheme == "sqlite"
    assert cfg["path"] == "emo_ai.db"


def test_parse_url_empty():
    scheme, cfg = _parse_url("")
    assert scheme == ""
    assert cfg == {}


# ── create_backend ─────────────────────────────────────────────

def test_create_backend_default():
    backend = create_backend()
    from core.db_backend import _SQLiteBackend
    assert isinstance(backend, _SQLiteBackend)
