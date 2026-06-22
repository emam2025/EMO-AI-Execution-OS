"""Parser abstraction layer for the AI Code Intelligence Layer.

This module provides a common interface for parsing different programming languages
to extract symbols, dependencies, annotations, and symbol relationships.

Each parser implements a parse() method that takes:
- file_path: Path to the file being parsed
- file_id: Database ID of the file
- content: File content as string

And returns a dictionary with:
- dependencies: list of import/export dependency dicts
- symbols: list of symbol dicts (functions, classes, etc.)
- symbol_relationships: list of call/inheritance edge dicts
- annotations: list of TODO/FIXME/etc. dicts
- file_metadata: list of key-value metadata dicts
"""

import ast
import hashlib
import json
import logging
import os
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

# Try to import tree-sitter
try:
    from tree_sitter import Language, Parser
    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False

from .ai_logging import get_ai_logger
from .static_analyzer import StaticAnalyzer

# Parser logger
parser_logger = get_ai_logger("parsers")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def build_call_relationship(
    source_symbol: str,
    target_symbol: str,
    call_type: str = "sync",
    signature: str | None = None,
    return_type: str | None = None,
    decorators: list | None = None,
) -> dict:
    """Build a single call relationship edge.

    Args:
        source_symbol: Name of the caller symbol (or "GLOBAL").
        target_symbol: Name of the callee symbol.
        call_type: One of "sync", "async", "generator".
        signature: String representation of the callee signature, or None.
        return_type: String return type annotation, or None.
        decorators: List of decorator strings for the callee.

    Returns:
        A relationship dict matching the standard output schema.
    """
    return {
        "source": source_symbol,
        "target": target_symbol,
        "edge_type": "call",
        "properties": {
            "call_count": 1,
            "call_type": call_type,
            "signature": signature,
            "return_type": return_type,
            "decorators": decorators or [],
        },
    }


def _get_function_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Extract a human-readable signature string from a function definition node."""
    args = []
    for arg in node.args.args:
        args.append(arg.arg)
    if node.args.vararg:
        args.append("*" + node.args.vararg.arg)
    for arg in node.args.kwonlyargs:
        args.append(arg.arg)
    if node.args.kwarg:
        args.append("**" + node.args.kwarg.arg)
    args_str = ", ".join(args)
    sig = f"{node.name}({args_str})"
    # Try to extract return annotation
    if node.returns and isinstance(node.returns, ast.Name):
        sig += f" -> {node.returns.id}"
    elif node.returns and isinstance(node.returns, ast.Subscript):
        # e.g. Optional[str] – just stringify the subscript
        try:
            sig += f" -> {ast.unparse(node.returns)}"
        except Exception:
            pass
    return sig


def _get_decorators(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> list[str]:
    """Extract decorator names from a function or class definition node."""
    decos = []
    for d in node.decorator_list:
        if isinstance(d, ast.Name):
            decos.append(d.id)
        elif isinstance(d, ast.Attribute):
            decos.append(d.attr)
        elif isinstance(d, ast.Call):
            # e.g. @app.route(...)
            if isinstance(d.func, ast.Attribute):
                decos.append(d.func.attr)
            elif isinstance(d.func, ast.Name):
                decos.append(d.func.id)
        else:
            try:
                decos.append(ast.unparse(d))
            except Exception:
                decos.append(str(d))
    return decos


def _get_return_type(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    """Extract return type annotation as a string, or None."""
    if node.returns is None:
        return None
    try:
        return ast.unparse(node.returns)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class LanguageParser(ABC):
    """Base class for language-specific parsers.

    Subclasses must implement parse() and return the standard schema dict.
    """

    def __init__(self):
        self.language_name = self.__class__.__name__.replace("Parser", "").lower()
        # Track the current function context for call attribution
        self.current_function: str | None = None

    @abstractmethod
    def parse(self, file_path: Path, file_id: int, content: str) -> dict:
        ...

    @staticmethod
    def _result(
        dependencies: list | None = None,
        symbols: list | None = None,
        symbol_relationships: list | None = None,
        annotations: list | None = None,
        file_metadata: list | None = None,
    ) -> dict:
        """Build a standard result dictionary."""
        return {
            "dependencies": dependencies or [],
            "symbols": symbols or [],
            "symbol_relationships": symbol_relationships or [],
            "annotations": annotations or [],
            "file_metadata": file_metadata or [],
        }


# ---------------------------------------------------------------------------
# Python Parser
# ---------------------------------------------------------------------------

class PythonParser(LanguageParser):
    """Parser for Python files using the built-in ast module."""

    def __init__(self):
        super().__init__()
        self.language_name = "python"

    def parse(self, file_path: Path, file_id: int, content: str) -> dict:

        # Build the result accumulators directly
        dependencies: list[dict] = []
        symbols: list[dict] = []
        symbol_relationships: list[dict] = []
        annotations: list[dict] = []
        file_metadata: list[dict] = [
            {"key": "language", "value": self.language_name},
            {"key": "syntax_valid", "value": "false"},
        ]

        try:
            tree = ast.parse(content)
            file_metadata = [
                {"key": "language", "value": self.language_name},
                {"key": "syntax_valid", "value": "true"},
            ]
        except SyntaxError as e:
            parser_logger.warning(f"Syntax error in {file_path}: {e}")
            # Still return metadata marking syntax invalid
            return self._result(
                dependencies=dependencies,
                symbols=symbols,
                symbol_relationships=symbol_relationships,
                annotations=annotations,
                file_metadata=file_metadata,
            )

        # ------------------------------------------------------------------
        # 1. Walk the AST to collect everything
        # ------------------------------------------------------------------
        for node in ast.walk(tree):
            # -- Imports ---------------------------------------------------
            if isinstance(node, ast.Import):
                for alias in node.names:
                    dependencies.append({
                        "type": "import",
                        "module": alias.name,
                        "alias": alias.asname,
                        "line": node.lineno,
                    })
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    dependencies.append({
                        "type": "from",
                        "module": module,
                        "name": alias.name,
                        "alias": alias.asname,
                        "line": node.lineno,
                    })

            # -- Function / AsyncFunction definitions ----------------------
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Determine call_type
                call_type = "async" if isinstance(node, ast.AsyncFunctionDef) else "sync"
                # Check if it's a generator via yield usage
                for child in ast.walk(node):
                    if isinstance(child, ast.Yield):
                        call_type = "generator"
                        break

                signature = _get_function_signature(node)
                decos = _get_decorators(node)
                return_type = _get_return_type(node)

                symbols.append({
                    "name": node.name,
                    "symbol_type": "function",
                    "line_number": node.lineno,
                    "column_number": node.col_offset,
                    "end_line": getattr(node, "end_lineno", node.lineno),
                    "end_column": getattr(node, "end_col_offset", node.col_offset + len(node.name)),
                    "signature": signature,
                    "docstring": ast.get_docstring(node) or "",
                    "call_type": call_type,
                    "return_type": return_type,
                    "decorators": decos,
                })

            # -- Class definitions -----------------------------------------
            elif isinstance(node, ast.ClassDef):
                # Extract base class names
                bases = []
                for base in node.bases:
                    if isinstance(base, ast.Name):
                        bases.append(base.id)
                    elif isinstance(base, ast.Attribute):
                        bases.append(base.attr)
                    else:
                        try:
                            bases.append(ast.unparse(base))
                        except Exception:
                            bases.append(str(base))

                bases_str = ", ".join(bases)
                signature = f"class {node.name}"
                if bases_str:
                    signature += f"({bases_str})"

                decos = _get_decorators(node)

                symbols.append({
                    "name": node.name,
                    "symbol_type": "class",
                    "line_number": node.lineno,
                    "column_number": node.col_offset,
                    "end_line": getattr(node, "end_lineno", node.lineno),
                    "end_column": getattr(node, "end_col_offset", node.col_offset + len(node.name)),
                    "signature": signature,
                    "docstring": ast.get_docstring(node) or "",
                    "call_type": None,
                    "return_type": None,
                    "decorators": decos,
                })

        # ------------------------------------------------------------------
        # 2. Static analysis enrichment (Phase 6)
        # ------------------------------------------------------------------
        static_analyzer = StaticAnalyzer()
        for sym in symbols:
            if sym["symbol_type"] == "function":
                analysis = static_analyzer.analyze_ast(tree, sym["name"])
                sym["static_analysis"] = analysis

        # ------------------------------------------------------------------
        # 3. Second pass: extract function calls with context tracking
        # ------------------------------------------------------------------
        self._extract_calls(tree, symbol_relationships)

        # ------------------------------------------------------------------
        # 3. Extract TODO-like annotations
        # ------------------------------------------------------------------
        self._extract_annotations(content, annotations)

        return self._result(
            dependencies=dependencies,
            symbols=symbols,
            symbol_relationships=symbol_relationships,
            annotations=annotations,
            file_metadata=file_metadata,
        )

    # -- Call extraction ---------------------------------------------------

    def _extract_calls(
        self,
        node: ast.AST,
        relationships: list[dict],
        current_func: str | None = None,
    ) -> None:
        """Recursively walk *node* and collect ast.Call nodes, tracking the
        enclosing function name as context.

        Each call is attributed to *current_func* (or "GLOBAL" when None).
        Nested FunctionDef/ClassDef nodes update the context for their
        subtree, then restore it afterward, ensuring a single visit per node.
        """
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._extract_calls(child, relationships, current_func=child.name)
                continue

            if isinstance(child, ast.ClassDef):
                self._extract_calls(child, relationships, current_func=current_func)
                continue

            if isinstance(child, ast.Call):
                target = self._get_call_name(child)
                if target is not None:
                    source = current_func or "GLOBAL"
                    if source != target:
                        relationships.append({
                            "source": source,
                            "target": target,
                            "edge_type": "call",
                            "properties": {
                                "call_count": 1,
                                "call_type": "sync",
                                "signature": None,
                                "return_type": None,
                                "decorators": [],
                            },
                        })
            else:
                self._extract_calls(child, relationships, current_func=current_func)

    @staticmethod
    def _get_call_name(node: ast.Call) -> str | None:
        """Extract the function name string from a Call node."""
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            return node.func.attr
        elif isinstance(node.func, ast.Subscript):
            try:
                return ast.unparse(node.func)
            except Exception:
                return None
        else:
            try:
                return ast.unparse(node.func)
            except Exception:
                return None

    # -- Annotation extraction --------------------------------------------

    @staticmethod
    def _extract_annotations(content: str, annotations: list[dict]) -> None:
        """Extract TODO/FIXME/HACK/XXX/NOTE comments."""
        patterns = [
            r'(#\s*)(TODO|FIXME|HACK|XXX|NOTE):?\s*(.*)',
            r'(//\s*)(TODO|FIXME|HACK|XXX|NOTE):?\s*(.*)',
            r'(/\*\s*)(TODO|FIXME|HACK|XXX|NOTE):?\s*(.*?)(\s*\*/)',
        ]
        lines = content.split("\n")
        for line_num, line in enumerate(lines, 1):
            for pat in patterns:
                m = re.search(pat, line, re.IGNORECASE)
                if m:
                    ann_type = m.group(2).upper() if m.group(2) else "TODO"
                    message = m.group(3).strip() if len(m.groups()) >= 3 else ""
                    col_offset = line.find(m.group(0))
                    annotations.append({
                        "annotation_type": ann_type,
                        "message": message,
                        "line_number": line_num,
                        "column_number": col_offset,
                    })
                    break


# ---------------------------------------------------------------------------
# JavaScript Parser (fallback mode, tree-sitter placeholder)
# ---------------------------------------------------------------------------

class JavaScriptParser(LanguageParser):
    """Parser for JavaScript files using tree-sitter with fallback to regex."""

    def __init__(self):
        super().__init__()
        self.language_name = "javascript"
        self.parser = None
        self.language = None
        self._initialize_tree_sitter()
        self.current_function = None

    def _initialize_tree_sitter(self):
        if not TREE_SITTER_AVAILABLE:
            parser_logger.debug("Tree-sitter not available, JS parser uses fallback")
            return
        # Placeholder – same as before
        parser_logger.debug("Tree-sitter JS grammar loading not fully implemented, using fallback")

    def parse(self, file_path: Path, file_id: int, content: str) -> dict:
        self.current_function = None

        result: dict = {
            "dependencies": [],
            "symbols": [],
            "symbol_relationships": [],
            "annotations": [],
            "file_metadata": [
                {"key": "language", "value": self.language_name},
                {"key": "syntax_valid", "value": "true"},
            ],
        }

        # Try tree-sitter if available
        if self.parser is not None and self.language is not None:
            try:
                return self._parse_with_tree_sitter(file_path, file_id, content)
            except Exception:
                parser_logger.warning(f"Tree-sitter JS failed for {file_path}, falling back")

        # Fallback
        self._extract_annotations(content, result["annotations"])
        self._extract_basic_dependencies(content, result["dependencies"])
        return result

    def _parse_with_tree_sitter(self, file_path, file_id, content) -> dict:
        """Tree-sitter JS — fallback to regex-based extraction."""
        result = {
            "dependencies": [],
            "symbols": [],
            "symbol_relationships": [],
            "annotations": [],
            "file_metadata": [
                {"key": "language", "value": self.language_name},
                {"key": "syntax_valid", "value": "true"},
                {"key": "parser", "value": "regex_fallback"},
            ],
        }
        self._extract_annotations(content, result["annotations"])
        self._extract_basic_dependencies(content, result["dependencies"])
        return result

    @staticmethod
    def _extract_annotations(content: str, annotations: list) -> None:
        patterns = [
            r'(#\s*)?(TODO|FIXME|HACK|XXX|NOTE):?\s*(.*)',
            r'(//\s*)?(TODO|FIXME|HACK|XXX|NOTE):?\s*(.*)',
            r'(/\*\s*)?(TODO|FIXME|HACK|XXX|NOTE):?\s*(.*?)(\s*\*/)',
        ]
        lines = content.split("\n")
        for line_num, line in enumerate(lines, 1):
            for pat in patterns:
                m = re.search(pat, line, re.IGNORECASE)
                if m:
                    ann_type = m.group(2).upper() if m.group(2) else "TODO"
                    message = m.group(3).strip() if len(m.groups()) >= 3 else ""
                    col_offset = line.find(m.group(0))
                    annotations.append({
                        "annotation_type": ann_type,
                        "message": message,
                        "line_number": line_num,
                        "column_number": col_offset,
                    })
                    break

    @staticmethod
    def _extract_basic_dependencies(content: str, dependencies: list) -> None:
        import_patterns = [
            r"""^\s*import\s+.*?\s+from\s+['"](.+?)['"]""",
            r"""^\s*import\s+['"](.+?)['"]""",
            r"""^\s*const\s+.*?\s*=\s*require\s*\(\s*['"](.+?)['"]\s*\)""",
            r"""^\s*require\s*\(\s*['"](.+?)['"]\s*\)""",
            r"""^\s*import\s+type\s+.*?\s+from\s+['"](.+?)['"]""",
        ]
        export_patterns = [
            r"""^\s*export\s+.*?\s+from\s+['"](.+?)['"]""",
        ]
        lines = content.split("\n")
        for line_num, line in enumerate(lines, 1):
            line = line.rstrip()
            if not line or line.startswith("//"):
                continue
            for pat in import_patterns:
                m = re.search(pat, line)
                if m:
                    module = m.group(1)
                    if not module.startswith("."):
                        dependencies.append({
                            "type": "import",
                            "module": module,
                            "line": line_num,
                        })
                    break
            for pat in export_patterns:
                m = re.search(pat, line)
                if m:
                    module = m.group(1)
                    if not module.startswith("."):
                        dependencies.append({
                            "type": "export",
                            "module": module,
                            "line": line_num,
                        })
                    break


# ---------------------------------------------------------------------------
# TypeScript Parser (fallback mode, tree-sitter placeholder)
# ---------------------------------------------------------------------------

class TypeScriptParser(LanguageParser):
    """Parser for TypeScript files using tree-sitter with fallback to regex."""

    def __init__(self):
        super().__init__()
        self.language_name = "typescript"
        self.parser = None
        self.language = None
        self._initialize_tree_sitter()
        self.current_function = None

    def _initialize_tree_sitter(self):
        if not TREE_SITTER_AVAILABLE:
            parser_logger.debug("Tree-sitter not available, TS parser uses fallback")
            return
        parser_logger.debug("Tree-sitter TS grammar loading not fully implemented, using fallback")

    def parse(self, file_path: Path, file_id: int, content: str) -> dict:
        self.current_function = None

        result: dict = {
            "dependencies": [],
            "symbols": [],
            "symbol_relationships": [],
            "annotations": [],
            "file_metadata": [
                {"key": "language", "value": self.language_name},
                {"key": "syntax_valid", "value": "true"},
            ],
        }

        if self.parser is not None and self.language is not None:
            try:
                return self._parse_with_tree_sitter(file_path, file_id, content)
            except Exception:
                parser_logger.warning(f"Tree-sitter TS failed for {file_path}, falling back")

        self._extract_annotations(content, result["annotations"])
        self._extract_basic_dependencies(content, result["dependencies"])
        return result

    def _parse_with_tree_sitter(self, file_path, file_id, content) -> dict:
        """Tree-sitter TS — fallback to regex-based extraction."""
        result = {
            "dependencies": [],
            "symbols": [],
            "symbol_relationships": [],
            "annotations": [],
            "file_metadata": [
                {"key": "language", "value": self.language_name},
                {"key": "syntax_valid", "value": "true"},
                {"key": "parser", "value": "regex_fallback"},
            ],
        }
        self._extract_annotations(content, result["annotations"])
        self._extract_basic_dependencies(content, result["dependencies"])
        return result

    @staticmethod
    def _extract_annotations(content: str, annotations: list) -> None:
        patterns = [
            r"(#\s*)?(TODO|FIXME|HACK|XXX|NOTE):?\s*(.*)",
            r"(//\s*)?(TODO|FIXME|HACK|XXX|NOTE):?\s*(.*)",
            r"(/\*\s*)?(TODO|FIXME|HACK|XXX|NOTE):?\s*(.*?)(\s*\*/)",
        ]
        lines = content.split("\n")
        for line_num, line in enumerate(lines, 1):
            for pat in patterns:
                m = re.search(pat, line, re.IGNORECASE)
                if m:
                    ann_type = m.group(2).upper() if m.group(2) else "TODO"
                    message = m.group(3).strip() if len(m.groups()) >= 3 else ""
                    col_offset = line.find(m.group(0))
                    annotations.append({
                        "annotation_type": ann_type,
                        "message": message,
                        "line_number": line_num,
                        "column_number": col_offset,
                    })
                    break

    @staticmethod
    def _extract_basic_dependencies(content: str, dependencies: list) -> None:
        import_patterns = [
            r"""^\s*import\s+.*?\s+from\s+['"](.+?)['"]""",
            r"""^\s*import\s+['"](.+?)['"]""",
            r"""^\s*const\s+.*?\s*=\s*require\s*\(\s*['"](.+?)['"]\s*\)""",
            r"""^\s*require\s*\(\s*['"](.+?)['"]\s*\)""",
            r"""^\s*import\s+type\s+.*?\s+from\s+['"](.+?)['"]""",
        ]
        export_patterns = [
            r"""^\s*export\s+.*?\s+from\s+['"](.+?)['"]""",
            r"""^\s*export\s+type\s+.*?\s+from\s+['"](.+?)['"]""",
        ]
        lines = content.split("\n")
        for line_num, line in enumerate(lines, 1):
            line = line.rstrip()
            if not line or line.startswith("//"):
                continue
            for pat in import_patterns:
                m = re.search(pat, line)
                if m:
                    module = m.group(1)
                    if not module.startswith("."):
                        dependencies.append({
                            "type": "import",
                            "module": module,
                            "line": line_num,
                        })
                    break
            for pat in export_patterns:
                m = re.search(pat, line)
                if m:
                    module = m.group(1)
                    if not module.startswith("."):
                        dependencies.append({
                            "type": "export",
                            "module": module,
                            "line": line_num,
                        })
                    break


# ---------------------------------------------------------------------------
# Fallback Parser
# ---------------------------------------------------------------------------

class FallbackParser(LanguageParser):
    """Fallback parser for unsupported file types."""

    def __init__(self):
        super().__init__()
        self.language_name = "unknown"

    def parse(self, file_path: Path, file_id: int, content: str) -> dict:
        annotations: list[dict] = []
        self._extract_annotations(content, annotations)
        return self._result(
            file_metadata=[{"key": "language", "value": self.language_name}],
            annotations=annotations,
        )

    @staticmethod
    def _extract_annotations(content: str, annotations: list) -> None:
        patterns = [
            r"(#\s*)?(TODO|FIXME|HACK|XXX|NOTE):?\s*(.*)",
            r"(//\s*)?(TODO|FIXME|HACK|XXX|NOTE):?\s*(.*)",
            r"(/\*\s*)?(TODO|FIXME|HACK|XXX|NOTE):?\s*(.*?)(\s*\*/)",
        ]
        lines = content.split("\n")
        for line_num, line in enumerate(lines, 1):
            for pat in patterns:
                m = re.search(pat, line, re.IGNORECASE)
                if m:
                    ann_type = m.group(2).upper() if m.group(2) else "TODO"
                    message = m.group(3).strip() if len(m.groups()) >= 3 else ""
                    col_offset = line.find(m.group(0))
                    annotations.append({
                        "annotation_type": ann_type,
                        "message": message,
                        "line_number": line_num,
                        "column_number": col_offset,
                    })
                    break


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def get_parser_for_extension(extension: str) -> LanguageParser:
    """Get the appropriate parser for a file extension.

    Args:
        extension: File extension (including the dot, e.g., '.py')

    Returns:
        LanguageParser instance for the extension
    """
    extension = extension.lower()

    if extension == ".py":
        return PythonParser()
    elif extension in (".js", ".jsx"):
        return JavaScriptParser()
    elif extension in (".ts", ".tsx"):
        return TypeScriptParser()
    else:
        return FallbackParser()
