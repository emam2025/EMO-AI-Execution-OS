from __future__ import annotations

import ast
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .determinism import sort_files


_SOURCE_EXTS = {".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs"}
_IGNORE_DIRS = {
    "__pycache__", "node_modules", ".git", ".venv", "venv",
    ".tox", "dist", "build", ".eggs", "*.egg-info",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
}
_IGNORE_FILES = {"__init__.py", "setup.py", "conftest.py"}

# Regex patterns for import extraction (fallback when AST fails)
_IMPORT_RE = re.compile(
    r"(?:^|\n)\s*(?:import\s+|from\s+(\S+)\s+import\s+)"
)


def discover_files(root: str) -> List[str]:
    """Stage 1a — scan filesystem, return sorted source file paths.

    Deterministic: alphabetical order, no randomness.
    """
    found: List[str] = []
    root_path = Path(root).resolve()
    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames[:] = [d for d in dirnames if d not in _IGNORE_DIRS]
        dirnames.sort()
        filenames.sort()
        for fname in filenames:
            if fname in _IGNORE_FILES:
                continue
            ext = Path(fname).suffix
            if ext in _SOURCE_EXTS:
                full = os.path.join(dirpath, fname)
                found.append(full)
    return sort_files(found)


class ParsedFile:
    """Result of parsing a single source file."""

    def __init__(
        self,
        path: str,
        raw_imports: List[str],
        classes: List[Tuple[str, int]],
        functions: List[Tuple[str, int]],
        interfaces: List[Tuple[str, int]],
        models: List[Tuple[str, int]],
        ast_body: Optional[ast.Module] = None,
    ):
        self.path = path
        self.raw_imports = raw_imports
        self.classes = classes
        self.functions = functions
        self.interfaces = interfaces
        self.models = models
        self.ast_body = ast_body


def parse_file(filepath: str) -> ParsedFile:
    """Stage 1b — parse a single file, extracting imports and symbol tables.

    Primary: AST parser (Python).
    Fallback: regex-based import extraction.
    """
    path = str(Path(filepath).resolve())
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
    except (OSError, IOError):
        return ParsedFile(path=path, raw_imports=[], classes=[], functions=[], interfaces=[], models=[])

    # Attempt AST parsing
    try:
        tree = ast.parse(source, filename=filepath)
        return _extract_from_ast(path, tree, source)
    except SyntaxError:
        pass

    # Fallback: regex import extraction
    imports = _extract_imports_regex(source)
    return ParsedFile(path=path, raw_imports=imports, classes=[], functions=[], interfaces=[], models=[])


def _extract_from_ast(path: str, tree: ast.Module, source: str) -> ParsedFile:
    imports: List[str] = []
    classes: List[Tuple[str, int]] = []
    functions: List[Tuple[str, int]] = []
    interfaces: List[Tuple[str, int]] = []
    models: List[Tuple[str, int]] = []

    for node in ast.walk(tree):
        # Import statements
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module:
                imports.append(module)
            for alias in node.names:
                full = f"{module}.{alias.name}" if module else alias.name
                imports.append(full)

        # Class definitions
        if isinstance(node, ast.ClassDef):
            classes.append((node.name, node.lineno or 0))
            for base in node.bases:
                if isinstance(base, ast.Name):
                    if "Protocol" in base.id or "ABC" in base.id:
                        interfaces.append((node.name, node.lineno or 0))

        # Function definitions (top-level only for cleanliness)
        if isinstance(node, ast.FunctionDef):
            functions.append((node.name, node.lineno or 0))

    # Detect @dataclass models
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for deco in node.decorator_list:
                if isinstance(deco, ast.Name) and deco.id == "dataclass":
                    models.append((node.name, node.lineno or 0))
                elif isinstance(deco, ast.Attribute) and deco.attr == "dataclass":
                    models.append((node.name, node.lineno or 0))

    return ParsedFile(
        path=path,
        raw_imports=imports,
        classes=classes,
        functions=functions,
        interfaces=interfaces,
        models=models,
        ast_body=tree,
    )


def _extract_imports_regex(source: str) -> List[str]:
    matches = _IMPORT_RE.findall(source)
    return [m.strip() for m in matches if m.strip()]
