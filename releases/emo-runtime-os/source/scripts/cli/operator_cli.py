#!/usr/bin/env python3
"""Phase K5 — Operator CLI: human-in-the-loop runtime commands.  # LAW-5 # LAW-8 # LAW-12

CLI interface wrapping IReadOnlyRuntimeAPI. No direct DB/EventStore access.
Every command generates operator_trace_id and emits an operator.action event.

LAW-K5-1: All reads go through ReadOnlyRuntimeAPI (read-only).
LAW-K5-2: All writes go through UnifiedRuntimeAPI via hooks.
LAW-K5-3: Every action carries operator_trace_id.
LAW-K5-4: No runtime forking.

Ref: EXEC-DIRECTIVE-027A §Task-2, §Task-3
Ref: Canon LAW 5, LAW 8, LAW 12
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
import uuid
from typing import Any, Dict, List, Optional

from core.runtime.api.operator_apis import ReadOnlyRuntimeAPI, OperatorTrace
from core.runtime.hooks.operator_hooks import OperatorHooks, OperatorActionRequest

logger = logging.getLogger("emo_ai.cli.operator")


def _operator_trace_id() -> str:
    return f"cli_{uuid.uuid4().hex[:12]}"


class OperatorCLI:
    """CLI entry point wrapping IReadOnlyRuntimeAPI and OperatorHooks.

    Never accesses DB or EventStore directly (LAW-K5-2).
    """

    def __init__(
        self,
        api: Optional[ReadOnlyRuntimeAPI] = None,
        hooks: Optional[OperatorHooks] = None,
    ) -> None:
        self._api = api or ReadOnlyRuntimeAPI()
        self._hooks = hooks or OperatorHooks(event_bus=None)

    # ── Handlers ─────────────────────────────────────────────────

    def handle_status(self, args: argparse.Namespace) -> int:
        ot = _operator_trace_id()
        self._api._trace("status", result="queried")
        health = self._api.get_runtime_health()
        dags = self._api.get_active_dags()
        print(f"Operator Trace: {ot}")
        print(f"Cluster:  {health.overall_status}")
        print(f"Active DAGs: {len(dags)}  Workers: {health.worker_count}")
        print(f"  healthy={health.healthy_workers} degraded={health.degraded_workers} offline={health.offline_workers}")
        print(f"Queues:   {health.queue_pressure:.0%} pressure")
        print(f"Latency:  p95={health.p95_latency_ms:.0f}ms  p99={health.p99_latency_ms:.0f}ms")
        if dags:
            for d in dags:
                print(f"  {d.dag_id}: {d.status} ({d.node_count} nodes, {d.total_duration_ms:.0f}ms)")
        return 0

    def handle_trace(self, args: argparse.Namespace) -> int:
        ot = _operator_trace_id()
        trace_id = args.trace_id
        self._api._trace("trace", target=trace_id)
        report = self._api.get_execution_trace(trace_id)
        tl = report.get("timeline", {})
        events = tl.get("events", report.get("spans", {}).get("events", []))
        print(f"Operator Trace: {ot}")
        print(f"Trace ID:   {trace_id}")
        print(f"Timeline:   {len(events)} events")
        for e in events[:10]:
            print(f"  {e}")
        if len(events) > 10:
            print(f"  ... and {len(events) - 10} more")
        return 0

    def handle_replay(self, args: argparse.Namespace) -> int:
        ot = _operator_trace_id()
        execution_id = args.execution_id
        checkpoint_id = getattr(args, "checkpoint_id", "") or ""
        self._api._trace("replay", target=execution_id)
        req = OperatorActionRequest(
            action="replay",
            target_id=execution_id,
            operator_trace_id=ot,
            params={"checkpoint_id": checkpoint_id} if checkpoint_id else {},
        )
        result = self._hooks.operator_replay(req)
        print(f"Operator Trace:  {ot}")
        print(f"Execution:       {execution_id}")
        print(f"Replay Result:   {result.status.value}")
        print(f"Replay ID:       {result.replay_id}")
        return 0

    def handle_worker(self, args: argparse.Namespace) -> int:
        ot = _operator_trace_id()
        self._api._trace("worker_topology")
        topology = self._api.get_worker_topology()
        print(f"Operator Trace: {ot}")
        for entry in topology:
            print(f"  {entry.get('type', '?')}: count={entry.get('count', 0)}")
        return 0

    def handle_pause(self, args: argparse.Namespace) -> int:
        ot = _operator_trace_id()
        execution_id = args.execution_id
        self._api._trace("pause", target=execution_id)
        req = OperatorActionRequest(action="pause", target_id=execution_id, operator_trace_id=ot)
        result = self._hooks.operator_pause(req)
        print(f"Operator Trace: {ot}")
        print(f"Execution:      {execution_id}")
        print(f"Status:         {result.status.value}")
        return 0

    def handle_resume(self, args: argparse.Namespace) -> int:
        ot = _operator_trace_id()
        execution_id = args.execution_id
        self._api._trace("resume", target=execution_id)
        req = OperatorActionRequest(action="resume", target_id=execution_id, operator_trace_id=ot)
        result = self._hooks.operator_resume(req)
        print(f"Operator Trace: {ot}")
        print(f"Execution:      {execution_id}")
        print(f"Status:         {result.status.value}")
        return 0

    def handle_force_retry(self, args: argparse.Namespace) -> int:
        ot = _operator_trace_id()
        execution_id = args.execution_id
        self._api._trace("force_retry", target=execution_id)
        req = OperatorActionRequest(action="force_retry", target_id=execution_id, operator_trace_id=ot)
        result = self._hooks.operator_force_retry(req)
        print(f"Operator Trace: {ot}")
        print(f"Execution:      {execution_id}")
        print(f"Status:         {result.status.value}")
        return 0

    def handle_traces(self, args: argparse.Namespace) -> int:
        ot = _operator_trace_id()
        traces = self._api.get_operator_traces(args.limit)
        print(f"Operator Trace: {ot}")
        print(f"{'Action':<20} {'Target':<30} {'Result':<12} {'Trace ID'}")
        print("-" * 90)
        for t in traces:
            print(f"{t.action:<20} {t.target:<30} {t.result:<12} {t.operator_trace_id}")
        return 0

    # ── Entry ────────────────────────────────────────────────────

    def run(self, argv: List[str]) -> int:
        parser = argparse.ArgumentParser(prog="emo", description="Emo-AI Operator CLI (K5)")
        sub = parser.add_subparsers(dest="command")

        p_status = sub.add_parser("status", help="Cluster health + active DAGs")
        p_status.set_defaults(handler=self.handle_status)

        p_trace = sub.add_parser("trace", help="Inspect execution trace")
        p_trace.add_argument("trace_id")
        p_trace.set_defaults(handler=self.handle_trace)

        p_replay = sub.add_parser("replay", help="Replay execution with optional checkpoint")
        p_replay.add_argument("execution_id")
        p_replay.add_argument("--checkpoint-id", default="")
        p_replay.set_defaults(handler=self.handle_replay)

        p_worker = sub.add_parser("worker", help="Worker topology view")
        p_worker.set_defaults(handler=self.handle_worker)

        p_pause = sub.add_parser("pause", help="Pause execution (human-in-the-loop)")
        p_pause.add_argument("execution_id")
        p_pause.set_defaults(handler=self.handle_pause)

        p_resume = sub.add_parser("resume", help="Resume paused execution")
        p_resume.add_argument("execution_id")
        p_resume.set_defaults(handler=self.handle_resume)

        p_retry = sub.add_parser("force-retry", help="Force retry of failed execution")
        p_retry.add_argument("execution_id")
        p_retry.set_defaults(handler=self.handle_force_retry)

        p_traces = sub.add_parser("traces", help="Operator action history")
        p_traces.add_argument("--limit", type=int, default=50)
        p_traces.set_defaults(handler=self.handle_traces)

        try:
            args = parser.parse_args(argv[1:])
        except SystemExit as e:
            return e.code
        if not getattr(args, "handler", None):
            parser.print_help()
            return 1
        return args.handler(args)


def main() -> None:
    sys.exit(OperatorCLI().run(sys.argv))


if __name__ == "__main__":
    main()
