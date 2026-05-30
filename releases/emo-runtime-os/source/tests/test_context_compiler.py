"""Tests for Context Compiler — context assembly as DAG-executable tools."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import warnings
warnings.filterwarnings("ignore")
import logging
logging.disable(logging.CRITICAL)

from unittest.mock import MagicMock, patch
from core.context_compiler import ContextCompiler, CONTEXT_COMPILER_VERSION
from core.ai_context_engine import AIContextEngine


def test_version():
    assert CONTEXT_COMPILER_VERSION == "1.0.0"


def test_version_property():
    cc = ContextCompiler(MagicMock(spec=AIContextEngine))
    assert cc.version == "1.0.0"


def test_build_llm_context_includes_symbol_id():
    mock_ctx = MagicMock(spec=AIContextEngine)
    mock_ctx.build_llm_context.return_value = {
        "system_context": "You are an AI...",
        "structured_context": {"symbol_context": {}, "graph_summary": {}},
        "llm_ready_prompt_block": "=== Symbol: foo ===",
    }
    cc = ContextCompiler(mock_ctx)
    result = cc.build_llm_context("foo")
    assert result["symbol_id"] == "foo"
    assert result["system_context"] == "You are an AI..."
    assert result["llm_ready_prompt_block"] == "=== Symbol: foo ==="
    mock_ctx.build_llm_context.assert_called_once_with("foo")


def test_build_llm_context_empty_symbol_id():
    cc = ContextCompiler(MagicMock(spec=AIContextEngine))
    result = cc.build_llm_context("")
    assert result["symbol_id"] == ""
    assert result["error"] == "No symbol_id provided"
    assert result["system_context"] == ""


def test_build_llm_context_delegates_to_engine():
    mock_ctx = MagicMock(spec=AIContextEngine)
    mock_ctx.build_llm_context.return_value = {
        "system_context": "test ctx",
        "structured_context": {"key": "val"},
        "llm_ready_prompt_block": "test block",
    }
    cc = ContextCompiler(mock_ctx)
    result = cc.build_llm_context("bar")
    assert result["system_context"] == "test ctx"
    assert result["structured_context"]["key"] == "val"
    assert result["llm_ready_prompt_block"] == "test block"


def test_build_symbol_context_includes_symbol_id():
    mock_ctx = MagicMock(spec=AIContextEngine)
    mock_ctx.build_symbol_context.return_value = {
        "symbol": {"name": "foo"},
        "callers": [],
        "callees": [],
        "neighbors": {},
        "summary_stats": {"importance_score": 42},
    }
    cc = ContextCompiler(mock_ctx)
    result = cc.build_symbol_context("foo")
    assert result["symbol_id"] == "foo"
    assert result["summary_stats"]["importance_score"] == 42


def test_build_symbol_context_delegates():
    mock_ctx = MagicMock(spec=AIContextEngine)
    cc = ContextCompiler(mock_ctx)
    cc.build_symbol_context("bar")
    mock_ctx.build_symbol_context.assert_called_once_with("bar")


def test_build_file_context_includes_file_id():
    mock_ctx = MagicMock(spec=AIContextEngine)
    mock_ctx.build_file_context.return_value = {
        "file": {"path": "/src/main.py"},
        "symbols": [],
        "dependencies": [],
        "impact_summary": [],
        "hotspots": [],
    }
    cc = ContextCompiler(mock_ctx)
    result = cc.build_file_context("file_1")
    assert result["file_id"] == "file_1"
    assert result["file"]["path"] == "/src/main.py"


def test_build_file_context_delegates():
    mock_ctx = MagicMock(spec=AIContextEngine)
    cc = ContextCompiler(mock_ctx)
    cc.build_file_context("file_x")
    mock_ctx.build_file_context.assert_called_once_with("file_x")


def test_result_is_dict_always():
    mock_ctx = MagicMock(spec=AIContextEngine)
    mock_ctx.build_llm_context.return_value = {}
    cc = ContextCompiler(mock_ctx)
    result = cc.build_llm_context("x")
    assert isinstance(result, dict)
    assert result["symbol_id"] == "x"


def test_all_tool_methods_return_dict():
    mock_ctx = MagicMock(spec=AIContextEngine)
    mock_ctx.build_llm_context.return_value = {"a": 1}
    mock_ctx.build_symbol_context.return_value = {"b": 2}
    mock_ctx.build_file_context.return_value = {"c": 3}
    cc = ContextCompiler(mock_ctx)
    assert isinstance(cc.build_llm_context("x"), dict)
    assert isinstance(cc.build_symbol_context("x"), dict)
    assert isinstance(cc.build_file_context("x"), dict)


def test_llm_context_full_structure():
    mock_ctx = MagicMock(spec=AIContextEngine)
    fake = {
        "system_context": "sys",
        "structured_context": {
            "symbol_context": {"symbol": {"name": "auth"}},
            "graph_summary": {"node_count": 5, "edge_count": 8},
            "risk_analysis": [],
            "key_dependencies": [],
            "hotspots": [],
        },
        "llm_ready_prompt_block": "=== Symbol: auth ===\nCallers: ...",
    }
    mock_ctx.build_llm_context.return_value = fake
    cc = ContextCompiler(mock_ctx)
    result = cc.build_llm_context("auth")
    assert "system_context" in result
    assert "structured_context" in result
    sc = result["structured_context"]
    assert sc["symbol_context"]["symbol"]["name"] == "auth"
    assert sc["graph_summary"]["node_count"] == 5


def test_not_using_engine_when_not_needed():
    """Empty symbol_id does not call the underlying engine."""
    mock_ctx = MagicMock(spec=AIContextEngine)
    cc = ContextCompiler(mock_ctx)
    cc.build_llm_context("")
    mock_ctx.build_llm_context.assert_not_called()
