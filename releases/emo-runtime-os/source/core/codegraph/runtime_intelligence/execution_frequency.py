"""3.8.1.5 — Execution Frequency Tracker.

Tracks execution frequency distributions across sessions.
Provides session-over-session trend analysis.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class FrequencyRecord:
    session_id: str = ""
    tool: str = ""
    execution_count: int = 0
    failure_count: int = 0

    @property
    def failure_rate(self) -> float:
        return self.failure_count / self.execution_count if self.execution_count > 0 else 0.0


@dataclass
class FrequencyTrend:
    tool: str = ""
    total_executions: int = 0
    session_count: int = 0
    avg_per_session: float = 0.0
    trend_direction: str = ""  # "increasing", "stable", "decreasing"


class ExecutionFrequencyTracker:
    """Aggregates execution frequency by tool across sessions.

    Enables trend analysis: which tools are being called more/less
    over time, and where retry pressure is concentrated.
    """

    def __init__(self):
        self._records: Dict[str, List[FrequencyRecord]] = defaultdict(list)

    def record_execution(
        self,
        session_id: str,
        tool: str,
        success: bool,
    ) -> None:
        existing = [r for r in self._records[tool] if r.session_id == session_id]
        if existing:
            existing[0].execution_count += 1
            if not success:
                existing[0].failure_count += 1
        else:
            self._records[tool].append(FrequencyRecord(
                session_id=session_id,
                tool=tool,
                execution_count=1,
                failure_count=0 if success else 1,
            ))

    def get_tool_frequency(self, tool: str) -> List[FrequencyRecord]:
        return list(self._records.get(tool, []))

    def get_all_frequencies(self) -> Dict[str, List[FrequencyRecord]]:
        return dict(self._records)

    def get_trend(self, tool: str) -> FrequencyTrend:
        records = self._records.get(tool, [])
        if not records:
            return FrequencyTrend(tool=tool)

        total = sum(r.execution_count for r in records)
        session_count = len(records)
        avg = total / session_count if session_count > 0 else 0.0

        if session_count < 2:
            return FrequencyTrend(
                tool=tool,
                total_executions=total,
                session_count=session_count,
                avg_per_session=avg,
                trend_direction="stable",
            )

        first_half = records[:len(records) // 2]
        second_half = records[len(records) // 2:]

        first_avg = sum(r.execution_count for r in first_half) / len(first_half)
        second_avg = sum(r.execution_count for r in second_half) / len(second_half)

        ratio = second_avg / first_avg if first_avg > 0 else 1.0
        if ratio > 1.2:
            direction = "increasing"
        elif ratio < 0.8:
            direction = "decreasing"
        else:
            direction = "stable"

        return FrequencyTrend(
            tool=tool,
            total_executions=total,
            session_count=session_count,
            avg_per_session=avg,
            trend_direction=direction,
        )

    def top_frequency(self, limit: int = 10) -> List[str]:
        tools_by_count = sorted(
            self._records.keys(),
            key=lambda t: sum(r.execution_count for r in self._records[t]),
            reverse=True,
        )
        return tools_by_count[:limit]
