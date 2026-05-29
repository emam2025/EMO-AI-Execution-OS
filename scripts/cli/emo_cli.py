#!/usr/bin/env python3
"""
EMO CLI — Command-line wrapper around EmoRuntimeFacade.

Usage:
    emo submit <intent> [--tenant TENANT] [--context KEY=VAL ...]
    emo status
    emo trace <trace_id>
    emo logs [--tail N]

Examples:
    emo submit summarize --tenant acme --context trace_snippets='[{"id":1}]'
    emo status
    emo trace og_abc123
    emo logs --tail 20
"""
import argparse
import asyncio
import json
import os
import sys
from typing import Any, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def _build_facade():
    from core.runtime.facade import EmoRuntimeFacade
    from core.orchestration.planner_agent import PlannerAgent
    from core.orchestration.critic_agent import CriticAgent
    from core.orchestration.optimizer_agent import OptimizerAgent
    from core.orchestration.orchestration_state_machine import OrchestrationStateMachine
    from core.orchestration.trace_correlator import OrchestrationTraceCorrelator

    return EmoRuntimeFacade(
        planner_agent=PlannerAgent(),
        critic_agent=CriticAgent(),
        optimizer_agent=OptimizerAgent(),
        orchestration_state_machine=OrchestrationStateMachine(),
        orchestration_trace_correlator=OrchestrationTraceCorrelator(),
    )


async def _cmd_submit(args):
    facade = _build_facade()
    context = {}
    if args.context:
        for kv in args.context:
            if "=" in kv:
                k, v = kv.split("=", 1)
                try:
                    context[k] = json.loads(v)
                except json.JSONDecodeError:
                    context[k] = v
    result = await facade.orchestrate(
        args.intent, args.tenant, context, {"max_cost_units": "100"},
    )
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("status") == "ok" else 1


async def _cmd_status(args):
    facade = _build_facade()
    health = facade.orchestration_health()
    print(json.dumps(health, indent=2))
    return 0


async def _cmd_trace(args):
    from core.orchestration.trace_correlator import OrchestrationTraceCorrelator
    ctc = OrchestrationTraceCorrelator()
    if args.trace_id:
        valid = ctc.verify_full_propagation(args.trace_id)
        events = ctc.get_events(args.trace_id) if hasattr(ctc, "get_events") else []
        print(json.dumps({"trace_id": args.trace_id, "valid": valid, "events": events}, indent=2))
    return 0


async def _cmd_logs(args):
    print(json.dumps({"message": "logs command requires runtime log integration", "tail": args.tail}))
    return 0


async def main():
    parser = argparse.ArgumentParser(description="EMO CLI — Cognitive Orchestration Client")
    sub = parser.add_subparsers(dest="command", required=True)

    p_submit = sub.add_parser("submit", help="Submit an intent for orchestration")
    p_submit.add_argument("intent", help="Natural language intent string")
    p_submit.add_argument("--tenant", default="default", help="Tenant ID (default: default)")
    p_submit.add_argument("--context", action="append", help="Context key=value pairs")

    p_status = sub.add_parser("status", help="Show orchestration health")

    p_trace = sub.add_parser("trace", help="Verify orchestration trace")
    p_trace.add_argument("trace_id", help="Orchestration trace ID (og_...)")

    p_logs = sub.add_parser("logs", help="Show recent logs")
    p_logs.add_argument("--tail", type=int, default=10, help="Number of log lines")

    args = parser.parse_args()

    handlers = {
        "submit": _cmd_submit,
        "status": _cmd_status,
        "trace": _cmd_trace,
        "logs": _cmd_logs,
    }

    handler = handlers.get(args.command)
    if handler:
        return await handler(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
