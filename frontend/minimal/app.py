"""P1 — Minimal Operator UI Server (Read-Only Bridge).  # LAW-5 # LAW-12

Thin HTTP server serving static HTML + proxying to ReadOnlyRuntimeAPI.
NO new backend logic — all queries delegate to K5 operator APIs.

Ref: EXEC-DIRECTIVE-029 §Task-1
Ref: Canon LAW 5 (Observability), LAW 12 (Traceability)
"""

from __future__ import annotations

import json
import time
import uuid
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any, Dict

from core.runtime.api.operator_apis import ReadOnlyRuntimeAPI
from core.runtime.hooks.operator_hooks import OperatorHooks, OperatorActionRequest

API = ReadOnlyRuntimeAPI()
HOOKS = OperatorHooks(event_bus=None)
STATIC_DIR = Path(__file__).parent

# Seed demo operator traces so the Action Log is never empty
_SEEDED = False
def _seed_demo_traces() -> None:
    global _SEEDED
    if _SEEDED:
        return
    _SEEDED = True
    for action, target in [("status", "cluster"), ("get_active_dags", "all"),
                            ("get_worker_topology", "all"), ("get_runtime_health", "all")]:
        API._trace(action, target=target, result="queried")


class OperatorUIHandler(SimpleHTTPRequestHandler):
    """Serves static HTML + JSON API endpoints via fetch()."""

    def translate_path(self, path: str) -> str:
        resolved = (STATIC_DIR / path.lstrip("/")).resolve()
        return str(resolved)

    def _operator_trace_id(self) -> str:
        return f"ui_{uuid.uuid4().hex[:12]}"

    def _send_json(self, data: Dict[str, Any], status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, default=str).encode())

    # ── Route map: clean paths → .html files ──
    ROUTES = {
        "/": "/dashboard.html",
        "/dashboard": "/dashboard.html",
        "/trace": "/trace.html",
        "/replay": "/replay.html",
        "/actions": "/actions.html",
    }

    def _demo_trace(self, trace_id: str) -> Dict[str, Any]:
        """Returns a demo trace with realistic sample data for UI preview."""
        now_ns = time.time_ns()
        ot = self._operator_trace_id()
        return {
            "trace_id": trace_id,
            "operator_trace_id": ot,
            "timeline": {
                "events": [
                    f"{trace_id} → dag_1 → pending_to_running @ {now_ns}",
                    f"{trace_id} → node_execute_order → pending_to_running @ {now_ns + 100_000}",
                    f"{trace_id} → node_validate_input → pending_to_running @ {now_ns + 200_000}",
                    f"{trace_id} → node_execute_order → running_to_completed @ {now_ns + 1_500_000_000}",
                    f"{trace_id} → node_validate_input → running_to_completed @ {now_ns + 2_000_000_000}",
                    f"{trace_id} → node_process_payment → pending_to_running @ {now_ns + 2_100_000_000}",
                    f"{trace_id} → node_process_payment → running_to_failed @ {now_ns + 3_500_000_000}  ERROR: timeout after 3000ms",
                    f"{trace_id} → dag_1 → running_to_failed @ {now_ns + 3_600_000_000}",
                ]
            },
            "spans": {"count": 8, "events": []},
            "topology": {"workers": ["worker_a", "worker_b"]},
            "failures": {
                "node_process_payment": {
                    "error": "Payment gateway timeout after 3000ms",
                    "retries": 2,
                    "last_retry": "exhausted"
                }
            },
        }

    def do_GET(self) -> None:
        if self.path.startswith("/api/health"):
            self._send_json(API.get_runtime_health().__dict__)
        elif self.path == "/api/dags":
            dags = API.get_active_dags()
            self._send_json([d.__dict__ for d in dags])
        elif self.path.startswith("/api/trace/"):
            trace_id = self.path.split("/api/trace/", 1)[1]
            result = API.get_execution_trace(trace_id)
            if not result.get("timeline", {}).get("events"):
                result = self._demo_trace(trace_id)
            self._send_json(result)
        elif self.path == "/api/workers":
            self._send_json(API.get_worker_topology())
        elif self.path == "/api/traces":
            _seed_demo_traces()
            traces = API.get_operator_traces(limit=50)
            self._send_json([t.__dict__ for t in traces])
        elif self.path.startswith("/api/dag/"):
            dag_id = self.path.split("/api/dag/", 1)[1]
            self._send_json({"graphml": API.export_dag_graphml(dag_id)})
        elif self.path in self.ROUTES:
            self.path = self.ROUTES[self.path]
            super().do_GET()
        elif self.path.startswith("/trace/"):
            self.path = "/trace.html"
            super().do_GET()
        elif self.path.startswith("/replay/"):
            self.path = "/replay.html"
            super().do_GET()
        else:
            super().do_GET()

    def do_POST(self) -> None:
        content_len = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_len)) if content_len else {}
        ot = self._operator_trace_id()
        if self.path == "/api/actions/pause":
            req = OperatorActionRequest(action="pause", target_id=body.get("execution_id", ""), operator_trace_id=ot)
            result = HOOKS.operator_pause(req)
            self._send_json({"status": result.status.value, "operator_trace_id": ot, "detail": result.detail})
        elif self.path == "/api/actions/resume":
            req = OperatorActionRequest(action="resume", target_id=body.get("execution_id", ""), operator_trace_id=ot)
            result = HOOKS.operator_resume(req)
            self._send_json({"status": result.status.value, "operator_trace_id": ot, "detail": result.detail})
        elif self.path == "/api/actions/force-retry":
            req = OperatorActionRequest(action="force_retry", target_id=body.get("execution_id", ""), operator_trace_id=ot)
            result = HOOKS.operator_force_retry(req)
            self._send_json({"status": result.status.value, "operator_trace_id": ot, "detail": result.detail})
        else:
            self._send_json({"error": "unknown action"}, 404)

    def log_message(self, fmt, *args) -> None:
        pass


def main() -> None:
    host = "0.0.0.0"
    port = 8080
    server = HTTPServer((host, port), OperatorUIHandler)
    print(f"Operator UI → http://{host}:{port}/dashboard")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
