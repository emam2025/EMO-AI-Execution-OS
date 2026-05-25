"""Failure Governance Layer — classify failures, suggest fixes (not retries).

Separates failure analysis from the retry mechanism in ExecutionEngine.
The FailureClassifier categorizes WHY something failed. The
FixSuggestionEngine provides actionable recommendations.

Failure classes:
    TOOL     — the tool implementation itself crashed or produced bad output
    ENGINE   — the execution engine infrastructure (timeout, pool, memory)
    DATA     — bad/missing input data, symbol not found, empty results
    SEMANTIC — the tool ran but the output is semantically wrong
    CONTRACT — input/output contract violation
    TIMEOUT  — execution exceeded time budget
    UNKNOWN  — cannot classify
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("emo_ai.failure_governance")


class FailureClass(str, Enum):
    TOOL = "tool"
    ENGINE = "engine"
    DATA = "data"
    SEMANTIC = "semantic"
    CONTRACT = "contract"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


# ═══════════════════════════════════════════════════════════════════════
# FailureClassifier
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class ClassifiedFailure:
    """Result of classifying a single node failure."""
    node_id: str
    tool: str
    failure_class: FailureClass
    error_message: str
    confidence: float          # 0.0 – 1.0
    suggestion: str = ""


class FailureClassifier:
    """Analyzes error messages and context to classify failures.

    Uses pattern matching on error text, tool name, and execution
    context to determine the failure class.
    """

    # Patterns that indicate each failure class
    TOOL_PATTERNS = [
        "attributeerror", "typeerror", "valueerror", "keyerror",
        "indexerror", "importerror", "modulenotfounderror",
        "zerodivisionerror", "runtimeerror",
    ]
    ENGINE_PATTERNS = [
        "brokenprocesspool", "cancellederror", "threadpool",
        "pool shutdown", "worker exception",
    ]
    DATA_PATTERNS = [
        "not found", "not_found", "no such", "missing",
        "empty", "no results", "no data", "symbol not",
        "not in index", "unresolved",
    ]
    CONTRACT_PATTERNS = [
        "contract violation", "missing required input",
        "missing required output", "unknown input", "unknown output",
    ]
    TIMEOUT_PATTERNS = [
        "timed out", "timeout", "time out",
    ]
    SEMANTIC_PATTERNS = [
        "semantic", "meaningless", "incoherent",
        "contradict", "irrelevant",
    ]

    @classmethod
    def classify(
        cls,
        tool: str,
        error: str,
        inputs: Optional[Dict[str, Any]] = None,
    ) -> ClassifiedFailure:
        """Classify a single failure based on error message and context."""
        error_lower = error.lower()
        node_id = inputs.get("node_id", "?") if inputs else "?"

        # Check contract violations first (most specific)
        for pat in cls.CONTRACT_PATTERNS:
            if pat in error_lower:
                return ClassifiedFailure(
                    node_id=node_id, tool=tool,
                    failure_class=FailureClass.CONTRACT,
                    error_message=error, confidence=0.95,
                    suggestion=cls._suggest_contract_fix(error),
                )

        # Check timeout
        for pat in cls.TIMEOUT_PATTERNS:
            if pat in error_lower:
                return ClassifiedFailure(
                    node_id=node_id, tool=tool,
                    failure_class=FailureClass.TIMEOUT,
                    error_message=error, confidence=0.95,
                    suggestion=cls._suggest_timeout_fix(tool),
                )

        # Check data issues
        for pat in cls.DATA_PATTERNS:
            if pat in error_lower:
                return ClassifiedFailure(
                    node_id=node_id, tool=tool,
                    failure_class=FailureClass.DATA,
                    error_message=error, confidence=0.9,
                    suggestion=cls._suggest_data_fix(tool),
                )

        # Check engine issues
        for pat in cls.ENGINE_PATTERNS:
            if pat in error_lower:
                return ClassifiedFailure(
                    node_id=node_id, tool=tool,
                    failure_class=FailureClass.ENGINE,
                    error_message=error, confidence=0.9,
                    suggestion=cls._suggest_engine_fix(),
                )

        # Check tool implementation issues
        for pat in cls.TOOL_PATTERNS:
            if pat in error_lower:
                return ClassifiedFailure(
                    node_id=node_id, tool=tool,
                    failure_class=FailureClass.TOOL,
                    error_message=error, confidence=0.85,
                    suggestion=cls._suggest_tool_fix(tool),
                )

        # Check for "remote-" prefix (service registry failure)
        if "remote-" in error_lower:
            return ClassifiedFailure(
                node_id=node_id, tool=tool,
                failure_class=FailureClass.ENGINE,
                error_message=error, confidence=0.8,
                suggestion=cls._suggest_remote_fix(tool),
            )

        # Default: unknown
        return ClassifiedFailure(
            node_id=node_id, tool=tool,
            failure_class=FailureClass.UNKNOWN,
            error_message=error, confidence=0.3,
            suggestion="Review the error manually. No automated fix available.",
        )

    # ── Suggestions ──────────────────────────────────────────

    @staticmethod
    def _suggest_contract_fix(error: str) -> str:
        if "Missing required input" in error:
            param = error.split("'")[1] if "'" in error else "unknown"
            return f"Add the required input parameter '{param}' to the node configuration."
        if "Missing required output" in error:
            param = error.split("'")[1] if "'" in error else "unknown"
            return f"The tool must return '{param}' in its output. Check the tool implementation."
        if "Unknown input" in error:
            return "Remove the unrecognized input parameter, or add it to the tool's contract."
        if "Unknown output" in error:
            return "Remove the unrecognized output, or add it to the tool's contract."
        return "Update the tool contract or fix the input/output to match the declared contract."

    @staticmethod
    def _suggest_timeout_fix(tool: str) -> str:
        return (f"Increase the timeout_seconds for '{tool}' in NodeConfig or ToolSpec. "
                f"Current timeout was too short for this operation.")

    @staticmethod
    def _suggest_data_fix(tool: str) -> str:
        if "symbol" in tool:
            return "The symbol was not found in the index. Re-index the repository or check the symbol name."
        return "The tool received empty or missing data. Ensure the repository is indexed and the query is valid."

    @staticmethod
    def _suggest_engine_fix() -> str:
        return "An execution engine infrastructure error occurred. Check worker pool health, memory store connectivity, and system resources."

    @staticmethod
    def _suggest_tool_fix(tool: str) -> str:
        return f"The tool '{tool}' raised an unexpected exception. Check the tool implementation for bugs, missing dependencies, or invalid state."

    @staticmethod
    def _suggest_remote_fix(tool: str) -> str:
        return f"The remote endpoint for '{tool}' is unreachable. Verify the service URL is correct and the remote worker is running."


# ═══════════════════════════════════════════════════════════════════════
# FixSuggestionEngine
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class FixSuggestion:
    """A single actionable fix suggestion for a classified failure."""
    node_id: str
    tool: str
    failure_class: FailureClass
    description: str
    priority: str = "medium"         # high / medium / low
    actionable: bool = True
    auto_fix_possible: bool = False


class FixSuggestionEngine:
    """Produces actionable fix suggestions for classified failures.

    Unlike FailureIntelligence (which tracks retry statistics),
    this engine provides human-readable recommendations for what
    to CHANGE, not what to RETRY.
    """

    @staticmethod
    def suggest(classified: ClassifiedFailure) -> FixSuggestion:
        """Generate a fix suggestion from a classified failure."""
        priority_map = {
            FailureClass.CONTRACT: "high",
            FailureClass.TIMEOUT: "medium",
            FailureClass.DATA: "high",
            FailureClass.ENGINE: "high",
            FailureClass.TOOL: "medium",
            FailureClass.SEMANTIC: "low",
            FailureClass.UNKNOWN: "low",
        }
        auto_fix_map = {
            FailureClass.TIMEOUT: True,
            FailureClass.CONTRACT: False,
            FailureClass.DATA: False,
            FailureClass.ENGINE: False,
            FailureClass.TOOL: False,
            FailureClass.SEMANTIC: False,
            FailureClass.UNKNOWN: False,
        }

        return FixSuggestion(
            node_id=classified.node_id,
            tool=classified.tool,
            failure_class=classified.failure_class,
            description=classified.suggestion,
            priority=priority_map.get(classified.failure_class, "medium"),
            actionable=classified.failure_class != FailureClass.UNKNOWN,
            auto_fix_possible=auto_fix_map.get(classified.failure_class, False),
        )

    @classmethod
    def suggest_batch(
        cls, classified_failures: List[ClassifiedFailure],
    ) -> List[FixSuggestion]:
        return [cls.suggest(cf) for cf in classified_failures]
