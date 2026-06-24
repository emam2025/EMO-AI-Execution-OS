"""Tests for parsers — LanguageParser ABC + JS/TS regex fallback."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import warnings
warnings.filterwarnings("ignore")
import logging
logging.disable(logging.CRITICAL)

from core.parsers import (
    LanguageParser,
    PythonParser,
    JavaScriptParser,
    TypeScriptParser,
    FallbackParser,
    get_parser_for_extension,
)
from pathlib import Path
from abc import ABC


# ── LanguageParser ABC ──────────────────────────────────────────

def test_language_parser_is_abstract():
    assert issubclass(LanguageParser, ABC)
    assert hasattr(LanguageParser, "parse")


def test_language_parser_cannot_instantiate():
    try:
        LanguageParser()
        assert False, "Should raise TypeError"
    except TypeError:
        pass


# ── get_parser_for_extension ────────────────────────────────────

def test_get_parser_python():
    p = get_parser_for_extension(".py")
    assert isinstance(p, PythonParser)


def test_get_parser_javascript():
    p = get_parser_for_extension(".js")
    assert isinstance(p, JavaScriptParser)
    p = get_parser_for_extension(".jsx")
    assert isinstance(p, JavaScriptParser)


def test_get_parser_typescript():
    p = get_parser_for_extension(".ts")
    assert isinstance(p, TypeScriptParser)
    p = get_parser_for_extension(".tsx")
    assert isinstance(p, TypeScriptParser)


def test_get_parser_fallback():
    p = get_parser_for_extension(".rs")
    assert isinstance(p, FallbackParser)
    p = get_parser_for_extension(".cpp")
    assert isinstance(p, FallbackParser)


# ── JavaScriptParser regex fallback ──────────────────────────────

JS_IMPORT_CONTENT = """
import { useState } from 'react';
const express = require('express');
import './local-module';
// comment
"""


def test_js_extract_imports():
    p = JavaScriptParser()
    result = p.parse(Path("test.js"), 1, JS_IMPORT_CONTENT)
    modules = [d["module"] for d in result["dependencies"]]
    assert "react" in modules
    assert "express" in modules
    assert "./local-module" not in modules  # relative, excluded


JS_ANNOTATION_CONTENT = """
// TODO: fix this
function foo() {
    // FIXME: major bug
    /* NOTE: important */
}
"""


def test_js_extract_annotations():
    p = JavaScriptParser()
    result = p.parse(Path("test.js"), 1, JS_ANNOTATION_CONTENT)
    types = [a["annotation_type"] for a in result["annotations"]]
    assert "TODO" in types
    assert "FIXME" in types
    assert "NOTE" in types


JS_EXPORT_CONTENT = """
export { foo } from 'lodash';
"""


def test_js_extract_export():
    p = JavaScriptParser()
    result = p.parse(Path("test.js"), 1, JS_EXPORT_CONTENT)
    exports = [d for d in result["dependencies"] if d["type"] == "export"]
    assert len(exports) == 1
    assert exports[0]["module"] == "lodash"


JS_EMPTY_CONTENT = """
// just a comment
"""


def test_js_empty_file():
    p = JavaScriptParser()
    result = p.parse(Path("empty.js"), 1, JS_EMPTY_CONTENT)
    assert result["dependencies"] == []
    assert result["annotations"] == []
    assert result["file_metadata"][0]["value"] == "javascript"


# ── TypeScriptParser regex fallback ─────────────────────────────

TS_IMPORT_CONTENT = """
import type { ReactNode } from 'react';
import { z } from 'zod';
import axios from 'axios';
"""


def test_ts_extract_imports():
    p = TypeScriptParser()
    result = p.parse(Path("test.ts"), 1, TS_IMPORT_CONTENT)
    modules = [d["module"] for d in result["dependencies"]]
    assert "react" in modules
    assert "zod" in modules
    assert "axios" in modules


TS_EXPORT_TYPE_CONTENT = """
export type { User } from './types';
export { api } from './api';
"""

TS_LOCAL_EXPORT_CONTENT = """
export { helper } from './helpers';
"""


def test_ts_export_type():
    p = TypeScriptParser()
    # local exports should be excluded
    result = p.parse(Path("test.ts"), 1, TS_LOCAL_EXPORT_CONTENT)
    exports = [d for d in result["dependencies"] if d["type"] == "export"]
    assert len(exports) == 0  # all relative -> excluded


# ── FallbackParser ──────────────────────────────────────────────

FALLBACK_CONTENT = """
# TODO: implement
/* FIXME: crash */
"""


def test_fallback_extract_annotations():
    p = FallbackParser()
    result = p.parse(Path("unknown.xyz"), 1, FALLBACK_CONTENT)
    types = [a["annotation_type"] for a in result["annotations"]]
    assert "TODO" in types
    assert "FIXME" in types


def test_fallback_language_name():
    p = FallbackParser()
    result = p.parse(Path("unknown.xyz"), 1, "")
    meta = {m["key"]: m["value"] for m in result["file_metadata"]}
    assert meta["language"] == "unknown"


# ── PythonParser ────────────────────────────────────────────────

PY_CONTENT = """
import os, sys
from typing import Optional

def greet(name: str) -> str:
    return f"Hello {name}"

class MyClass:
    pass
"""


def test_python_parse_basic():
    p = PythonParser()
    result = p.parse(Path("test.py"), 1, PY_CONTENT)
    assert len(result["dependencies"]) >= 2
    names = [s["name"] for s in result["symbols"]]
    assert "greet" in names
    assert "MyClass" in names
    meta = {m["key"]: m["value"] for m in result["file_metadata"]}
    assert meta["syntax_valid"] == "true"


PY_SYNTAX_ERROR = """
def broken(:
"""


def test_python_syntax_error():
    p = PythonParser()
    result = p.parse(Path("broken.py"), 1, PY_SYNTAX_ERROR)
    meta = {m["key"]: m["value"] for m in result["file_metadata"]}
    assert meta["syntax_valid"] == "false"
