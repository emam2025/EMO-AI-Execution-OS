"""Observability Domain Models.

Pure data structures using stdlib only. Zero internal imports.

Ref: P10.1 — Observability Foundation (Metrics & Tracing)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from uuid import uuid4

# SpanStatus is canonical from runtime models
from core.runtime.models.observability_models import SpanStatus  # noqa: F401


class MetricType(Enum):
    """Types of metrics collected."""

    LATENCY = "latency"
    ERROR_RATE = "error_rate"
    THROUGHPUT = "throughput"


@dataclass(frozen=True)
class Span:
    """A single span in a distributed trace."""

    span_id: str = field(default_factory=lambda: str(uuid4()))
    trace_id: str = ""
    operation: str = ""
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: Optional[datetime] = None
    status: SpanStatus = SpanStatus.UNSET
    metadata: Dict[str, Any] = field(default_factory=dict)
