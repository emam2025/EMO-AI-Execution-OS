"""Static Analysis Engine – Phase 6 Symbol Intelligence.

Pure AST-based analysis layer that enriches symbols with behavioral
intelligence, complexity estimates, and role classification.

No database access, no graph mutations.  Deterministic and side-effect
free.
"""

import ast
import re
from typing import Any, Dict, List, Optional, Set


# ── Helpers ─────────────────────────────────────────────────────────────

_IO_INDICATORS: Set[str] = {
    "print", "open", "read", "write", "close", "flush",
    "input", "stdout", "stderr", "stdin",
}

_DB_INDICATORS: Set[str] = {
    "execute", "cursor", "commit", "rollback", "fetchone",
    "fetchall", "fetchmany", "query", "select", "insert",
    "update", "delete", "sql", "connect",
}

_DB_KEYWORD_PATTERN = re.compile(
    r"(SELECT\b|INSERT\b|UPDATE\b|DELETE\b|CREATE\b|DROP\b|ALTER\b|FROM\b|"
    r"WHERE\b|JOIN\b)",
    re.IGNORECASE,
)


# ── StaticAnalyzer ─────────────────────────────────────────────────────

class StaticAnalyzer:
    """Pure static analysis of a single Python function symbol.

    Usage:
        analyzer = StaticAnalyzer()
        result = analyzer.analyze(source_code, symbol_name)
    """

    def analyze(self, source_code: str, symbol_name: str) -> Dict[str, Any]:
        """Analyze a symbol within Python source code.

        Args:
            source_code: Full file source as a string.
            symbol_name: Name of the function to analyse.

        Returns:
            Dict with keys: symbol_id (set to symbol_name for now),
            behavior, complexity, role, call_profile.
        """
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return self._empty_result(symbol_name)
        return self.analyze_ast(tree, symbol_name)

    def analyze_ast(self, tree: ast.Module, symbol_name: str) -> Dict[str, Any]:
        """Analyze a symbol from an already-parsed AST.

        Same as ``analyze()`` but avoids re-parsing the source string.
        Use this when the caller already has a parsed ``ast.Module``.
        """
        target_node = self._find_function(tree, symbol_name)
        if target_node is None:
            return self._empty_result(symbol_name)

        # Collect all function names defined in the file
        defined_functions = self._collect_function_names(tree)

        return self._analyze_node(target_node, symbol_name, defined_functions)

    # ── internal analysis ───────────────────────────────────────────────

    def _analyze_node(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        symbol_name: str,
        defined_functions: Set[str],
    ) -> Dict[str, Any]:
        """Analyse a single function definition node."""

        is_async = isinstance(node, ast.AsyncFunctionDef)

        # Walk once to collect all interesting children
        calls: List[ast.Call] = []
        yields: List[ast.Yield] = []
        awaits: List[ast.Await] = []
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                calls.append(child)
            elif isinstance(child, ast.Yield):
                yields.append(child)
            elif isinstance(child, ast.Await):
                awaits.append(child)

        # Recursion
        target_calls = [
            c for c in calls
            if isinstance(c.func, ast.Name) and c.func.id == symbol_name
        ]
        is_recursive = len(target_calls) > 0
        recursion_depth = self._estimate_recursion_depth(node, symbol_name)

        # Async call detection: calls that are directly inside a ``with``
        # ``await expr`` are counted as async.
        async_call_ids: Set[int] = set()
        for await_node in awaits:
            for child in ast.walk(await_node.value):
                if isinstance(child, ast.Call):
                    async_call_ids.add(id(child))

        sync_calls = 0
        async_calls = 0
        generator_calls = 0
        for call in calls:
            if id(call) in async_call_ids:
                async_calls += 1
            else:
                sync_calls += 1
        generator_calls = len(yields)

        # Ensure minimum counts
        if is_async:
            async_calls = max(async_calls, 1)
        if generator_calls > 0:
            generator_calls = max(generator_calls, 1)

        # Complexity ------------------------------------------------------
        branches = sum(
            1 for _ in ast.walk(node)
            if isinstance(_, ast.If)
        )
        loops = sum(
            1 for _ in ast.walk(node)
            if isinstance(_, (ast.For, ast.While, ast.AsyncFor))
        )
        try_blocks = sum(
            1 for _ in ast.walk(node)
            if isinstance(_, ast.Try)
        )
        decisions = sum(
            1 for _ in ast.walk(node)
            if isinstance(_, (ast.If, ast.While, ast.For, ast.AsyncFor,
                              ast.ExceptHandler, ast.Assert,
                              ast.BoolOp))
        )
        bool_ops = sum(
            len(child.values) - 1
            for child in ast.walk(node)
            if isinstance(child, ast.BoolOp)
        )
        cyclomatic = 1 + decisions + bool_ops

        # DB keyword detection (SQL strings + method attrs) ---------------
        has_db_keywords = self._detect_db_keywords(node)

        # Role classification --------------------------------------------
        role = self._classify_role(
            node, symbol_name, defined_functions,
            sync_calls, async_calls, generator_calls,
            is_async, cyclomatic, has_db_keywords,
        )

        return {
            "symbol_id": symbol_name,
            "behavior": {
                "is_async": is_async,
                "is_recursive": is_recursive,
                "recursion_depth": recursion_depth,
            },
            "complexity": {
                "cyclomatic": cyclomatic,
                "branches": branches,
                "loops": loops,
                "try_blocks": try_blocks,
            },
            "role": role,
            "call_profile": {
                "sync_calls": sync_calls,
                "async_calls": async_calls,
                "generator_calls": generator_calls,
            },
        }

    # ── db keyword detection ────────────────────────────────────────────

    @staticmethod
    def _detect_db_keywords(node: ast.AST) -> bool:
        """Detect SQL-like patterns and DB method calls in a function node.

        Checks two things:
        1. String constants containing SQL keywords (SELECT, INSERT, …)
        2. Method calls whose attribute name matches ``_DB_INDICATORS``
        """
        for child in ast.walk(node):
            # SQL strings
            if isinstance(child, ast.Constant) and isinstance(child.value, str):
                if _DB_KEYWORD_PATTERN.search(child.value):
                    return True
            # Method calls like ``.execute(…)``, ``.fetchone(…)``
            if (isinstance(child, ast.Call)
                    and isinstance(child.func, ast.Attribute)):
                if child.func.attr in _DB_INDICATORS:
                    return True
        return False

    # ── recursion depth estimation ──────────────────────────────────────

    def _estimate_recursion_depth(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        symbol_name: str,
    ) -> int:
        """Estimate recursion depth heuristically.

        Checks three patterns in order:
        1.  Direct call to self inside a loop → depth = 3 (likely deep)
        2.  Direct call inside an if branch    → depth = 2 (conditional)
        3.  Direct tail-call at end of body    → depth = 1 (base case)

        Otherwise returns 1 if any self-call exists, else 0.
        """
        inside_loop = False
        inside_if = False
        is_tail = False
        has_self_call = False

        body_statements = node.body

        for stmt in body_statements:
            if isinstance(stmt, (ast.For, ast.While, ast.AsyncFor)):
                inside_loop = True
                for child in ast.walk(stmt):
                    if (isinstance(child, ast.Call)
                            and isinstance(child.func, ast.Name)
                            and child.func.id == symbol_name):
                        has_self_call = True

            if isinstance(stmt, ast.If):
                for child in ast.walk(stmt):
                    if (isinstance(child, ast.Call)
                            and isinstance(child.func, ast.Name)
                            and child.func.id == symbol_name):
                        inside_if = True
                        has_self_call = True

            for child in ast.walk(stmt):
                if (isinstance(child, ast.Call)
                        and isinstance(child.func, ast.Name)
                        and child.func.id == symbol_name):
                    has_self_call = True

        if body_statements:
            last = body_statements[-1]
            if isinstance(last, ast.Expr) and isinstance(last.value, ast.Call):
                if (isinstance(last.value.func, ast.Name)
                        and last.value.func.id == symbol_name):
                    is_tail = True
            elif isinstance(last, ast.Return):
                val = last.value
                if isinstance(val, ast.Call):
                    if (isinstance(val.func, ast.Name)
                            and val.func.id == symbol_name):
                        is_tail = True

        if inside_loop:
            return 3
        if inside_if:
            return 2
        if is_tail:
            return 1
        if has_self_call:
            return 1
        return 0

    # ── role classification ─────────────────────────────────────────────

    def _classify_role(
        self,
        node: ast.AST,
        symbol_name: str,
        defined_functions: Set[str],
        sync_calls: int,
        async_calls: int,
        generator_calls: int,
        is_async: bool,
        cyclomatic: int,
        has_db_keywords: bool,
    ) -> str:
        """Classify a function's role using static heuristics.

        Detects DB/IO indicators from:
        - ``ast.Name`` calls (bare names like ``open(…)``)
        - ``ast.Attribute`` calls (method calls like ``conn.execute(…)``)
        - SQL string detection (``has_db_keywords``)
        """
        has_io = False
        has_db = False
        has_yield = generator_calls > 0
        calls_external = 0
        defined_calls = 0

        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue

            if isinstance(child.func, ast.Name):
                name = child.func.id
                if name in _IO_INDICATORS:
                    has_io = True
                if name in _DB_INDICATORS:
                    has_db = True
                if name in defined_functions and name != symbol_name:
                    defined_calls += 1
                elif name not in defined_functions:
                    calls_external += 1

            elif isinstance(child.func, ast.Attribute):
                attr = child.func.attr
                if attr in _IO_INDICATORS:
                    has_io = True
                if attr in _DB_INDICATORS:
                    has_db = True

        # Merge SQL string / attribute detection into the db flag
        has_db = has_db or has_db_keywords

        total_calls = sync_calls + async_calls + generator_calls

        # Heuristic rules (order matters – first match wins)
        if has_yield:
            return "generator"
        if is_async and has_db:
            return "data_access"
        if has_db and cyclomatic > 3:
            return "data_access"
        if has_io and total_calls > 0:
            return "io_bound"
        if cyclomatic > 5 and defined_calls > 2:
            return "orchestrator"
        if defined_calls > 1 and calls_external > 0:
            return "controller"
        if calls_external > 1 and cyclomatic > 1:
            return "controller"
        if total_calls == 0 or (total_calls == 1 and not has_db and not has_io):
            return "pure_function"
        if calls_external > defined_calls:
            return "utility"
        if cyclomatic > 3:
            return "controller"

        return "utility"

    # ── AST helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _find_function(
        tree: ast.Module,
        symbol_name: str,
    ) -> Optional[ast.FunctionDef | ast.AsyncFunctionDef]:
        """Find the first function definition matching *symbol_name*."""
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == symbol_name:
                    return node
        return None

    @staticmethod
    def _collect_function_names(tree: ast.Module) -> Set[str]:
        """Collect all function names defined in the AST."""
        names: Set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names.add(node.name)
        return names

    @staticmethod
    def _empty_result(symbol_name: str) -> Dict[str, Any]:
        """Return a safe empty result when analysis fails."""
        return {
            "symbol_id": symbol_name,
            "behavior": {
                "is_async": False,
                "is_recursive": False,
                "recursion_depth": 0,
            },
            "complexity": {
                "cyclomatic": 1,
                "branches": 0,
                "loops": 0,
                "try_blocks": 0,
            },
            "role": "unknown",
            "call_profile": {
                "sync_calls": 0,
                "async_calls": 0,
                "generator_calls": 0,
            },
        }
