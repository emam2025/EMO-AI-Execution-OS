"""Sandbox Domain Models — Execution Isolation Data Structures.

Pure data structures using stdlib only. Zero internal imports.
Frozen dataclasses for sandbox context and execution results.

Ref: Phase E.1.2 — Sandboxed Executor (Subprocess Isolation)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple


@dataclass(frozen=True)
class SandboxContext:
    """Execution context for a sandboxed tool invocation.

    Defines resource limits and isolation parameters.
    """

    tool_id: str = ""
    timeout_seconds: float = 30.0
    max_memory_mb: int = 256
    max_cpu_seconds: float = 10.0
    allowed_paths: Tuple[str, ...] = ()
    allowed_domains: Tuple[str, ...] = ()


@dataclass(frozen=True)
class SandboxResult:
    """Result of a sandboxed execution.

    Contains output, error info, resource usage telemetry,
    and status flags for timeout/killed scenarios.
    """

    success: bool = False
    output: str = ""
    error: str = ""
    exit_code: int = -1
    duration_seconds: float = 0.0
    peak_memory_mb: float = 0.0
    timed_out: bool = False
    killed: bool = False
