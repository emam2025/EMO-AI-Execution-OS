"""Pilot Launcher — starts Operator UI with strict_pilot_mode=True.  # LAW-5 # LAW-12

Launches frontend/minimal/app.py with isolated user contexts,
strict_pilot_mode=True, and pilot_trace_id propagation.

Ref: EXEC-DIRECTIVE-PILOT-001 §Task-3
Ref: Canon LAW 5, LAW 11, LAW 12
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

BASE = Path(__file__).resolve().parent.parent.parent


class PilotLauncher:
    """Launches and manages the Operator UI pilot instance."""

    def __init__(
        self,
        port: int = 8080,
        host: str = "0.0.0.0",
        pilot_trace_id: str = "",
        strict_pilot_mode: bool = True,
    ) -> None:
        self._port = port
        self._host = host
        self._pilot_trace_id = pilot_trace_id or f"pilot_launcher_{int(time.time())}"
        self._strict_pilot_mode = strict_pilot_mode
        self._process: Optional[subprocess.Popen] = None

    def launch(self) -> Dict[str, object]:
        """Start the Operator UI server with pilot mode."""
        env = os.environ.copy()
        env["PYTHONPATH"] = str(BASE)
        env["PILOT_TRACE_ID"] = self._pilot_trace_id
        env["STRICT_PILOT_MODE"] = "1" if self._strict_pilot_mode else "0"

        app_path = str(BASE / "frontend" / "minimal" / "app.py")
        cmd = [sys.executable, app_path]

        self._process = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        time.sleep(1.5)

        import urllib.request
        try:
            r = urllib.request.urlopen(f"http://{self._host}:{self._port}/api/health", timeout=3)
            status = "RUNNING"
            detail = f"HTTP {r.status}"
        except Exception as e:
            status = "FAILED"
            detail = str(e)

        result = {
            "pilot_trace_id": self._pilot_trace_id,
            "host": self._host,
            "port": self._port,
            "status": status,
            "detail": detail,
            "pid": self._process.pid if self._process else None,
            "strict_pilot_mode": self._strict_pilot_mode,
        }

        log_path = BASE / "artifacts" / "pilot" / "launch_log.json"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "w") as f:
            json.dump(result, f, indent=2)

        return result

    def shutdown(self) -> None:
        if self._process:
            self._process.terminate()
            self._process.wait(timeout=5)
            self._process = None

    def health(self) -> Dict[str, object]:
        import urllib.request
        try:
            r = urllib.request.urlopen(f"http://{self._host}:{self._port}/api/health", timeout=3)
            data = json.loads(r.read())
            return {"status": "healthy", "data": data}
        except Exception as e:
            return {"status": "unreachable", "error": str(e)}


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    launcher = PilotLauncher(port=port)
    result = launcher.launch()
    print(json.dumps(result, indent=2))
    if result["status"] == "RUNNING":
        print(f"Pilot UI → http://{result['host']}:{result['port']}/dashboard")
    else:
        print(f"Launch failed: {result['detail']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
