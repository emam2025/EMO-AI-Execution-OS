
"""Refactored project intelligence tools for Emo AI.

This module improves safety, readability, and runtime correctness while
preserving the original feature set:
- AutoDebugger
- AICodeReviewer
- ProjectMonitor
- ProjectScaffold
- ProjectAnalyzer
- DependencyManager
- CodebaseRefactor
- DeploymentBuilder
"""

from __future__ import annotations

import ast
import builtins
import json
import logging
import os
import queue
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Optional external dependencies
# ---------------------------------------------------------------------------
try:
    from tools import Tool
except ImportError:  # pragma: no cover - fallback for standalone use
    class Tool:  # type: ignore
        name = ""
        description = ""
        category = ""
        icon = ""
        parameters: Dict[str, str] = {}

        def __init__(self, *args, **kwargs):
            pass

try:
    from brain import Brain  # type: ignore
    BRAIN_AVAILABLE = True
except ImportError:  # pragma: no cover
    Brain = None  # type: ignore
    BRAIN_AVAILABLE = False


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("emo-ai")


# ---------------------------------------------------------------------------
# Paths and safety helpers
# ---------------------------------------------------------------------------
# Isolated workspace root - AI can ONLY access files inside this directory
# This prevents AI from reading Emo AI's own source code, keys, or database
WORKSPACE_ROOT = Path(__file__).parent.resolve() / "user_projects"
WORKSPACE_ROOT.mkdir(exist_ok=True)

EMO_AI_PROJECT_DIR = Path(__file__).parent.resolve()  # Emo AI's own directory (BLOCKED)

ALLOWED_COMMANDS = {
    "npm",
    "pip",
    "python",
    "python3",
    "node",
    "npx",
    "vercel",
    "firebase",
    "docker",
    "docker-compose",
    "git",
}


def _safe_path(path: Path, *, must_exist: bool = False) -> Path:
    """Resolve a path and ensure it's within the isolated user workspace.
    
    SECURITY: Blocks access to Emo AI's own project files, system directories,
    and any path outside the user_projects workspace.
    """
    resolved = path.expanduser().resolve()

    # Check if path is inside workspace
    try:
        resolved.relative_to(WORKSPACE_ROOT)
        if must_exist and not resolved.exists():
            raise FileNotFoundError(f"Path not found: {resolved}")
        return resolved
    except ValueError:
        pass  # Not in workspace, check further

    # If path doesn't exist yet (e.g., creating new file), check parent
    if not must_exist and not resolved.exists():
        parent = resolved.parent
        try:
            parent.relative_to(WORKSPACE_ROOT)
            return resolved
        except ValueError:
            pass

    # Determine appropriate error message
    try:
        resolved.relative_to(EMO_AI_PROJECT_DIR)
        raise ValueError("Access denied: Cannot access Emo AI system files")
    except ValueError as e:
        if "Emo AI" in str(e):
            raise
        raise ValueError(f"Access denied: Path outside workspace ({resolved})")


def _fmt_size(size: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f}{unit}"
        value /= 1024
    return f"{value:.1f}TB"


def _command_exists(cmd: str) -> bool:
    try:
        subprocess.run([cmd, "--version"], capture_output=True, timeout=5, check=False)
        return True
    except (FileNotFoundError, subprocess.SubprocessError):
        return False


def _run_command(args: List[str], cwd: Path, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _is_hidden_path(path: Path) -> bool:
    return any(part.startswith(".") for part in path.parts)


def _unique_destination(path: Path) -> Path:
    """Return a non-colliding destination path by adding a numeric suffix."""
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    for i in range(1, 1000):
        candidate = parent / f"{stem}_{i}{suffix}"
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"Could not find free destination for {path}")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------
PROJECT_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "react": {
        "files": {
            "package.json": json.dumps(
                {
                    "name": "my-app",
                    "version": "1.0.0",
                    "private": True,
                    "dependencies": {
                        "react": "^18.2.0",
                        "react-dom": "^18.2.0",
                    },
                    "scripts": {
                        "start": "react-scripts start",
                        "build": "react-scripts build",
                    },
                },
                indent=2,
            ),
            "public/index.html": """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>React App</title>
</head>
<body>
  <div id="root"></div>
</body>
</html>
""",
            "src/App.js": """import React from 'react';

function App() {
  return <div><h1>Hello from Emo AI</h1></div>;
}

export default App;
""",
            "src/index.js": """import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App />);
""",
        },
        "install": ["npm", "install"],
        "description": "React frontend with npm (React 18)",
    },
    "fastapi": {
        "files": {
            "main.py": """from fastapi import FastAPI

app = FastAPI(title="Emo AI Project")

@app.get("/")
async def root():
    return {"message": "Hello from Emo AI"}
""",
            "requirements.txt": "fastapi\nuvicorn\n",
            "Dockerfile": """FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -r requirements.txt
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
""",
        },
        "install": ["pip", "install", "-r", "requirements.txt"],
        "description": "FastAPI backend with Python",
    },
    "html": {
        "files": {
            "index.html": """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Emo AI Project</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <h1>Emo AI Project</h1>
  <p>Created by Emam AbdullAziz</p>
</body>
</html>
""",
            "style.css": "body{font-family:system-ui,sans-serif;max-width:800px;margin:auto;padding:2rem;line-height:1.5}\n",
        },
        "install": [],
        "description": "Static HTML/CSS site",
    },
    "node": {
        "files": {
            "package.json": json.dumps(
                {
                    "name": "my-app",
                    "version": "1.0.0",
                    "private": True,
                    "main": "index.js",
                    "scripts": {"start": "node index.js"},
                    "dependencies": {"express": "^4.18.0"},
                },
                indent=2,
            ),
            "index.js": """const express = require('express');
const app = express();
const port = process.env.PORT || 3000;

app.get('/', (req, res) => res.json({ message: 'Hello from Emo AI' }));
app.listen(port, () => console.log(`Server on port ${port}`));
""",
        },
        "install": ["npm", "install"],
        "description": "Node.js/Express backend",
    },
    "python": {
        "files": {
            "main.py": """def main():
    print('Hello from Emo AI!')


if __name__ == '__main__':
    main()
""",
            "requirements.txt": "# Add your dependencies here\n",
            "README.md": "# Emo AI Project\n\nCreated by Emam AbdullAziz.\n",
        },
        "install": ["pip", "install", "-r", "requirements.txt"],
        "description": "Basic Python project",
    },
}

GITIGNORE_CONTENT = """# Python
__pycache__/
*.py[cod]
*.so
.Python
env/
venv/
.env
.venv
*.egg-info/
dist/
build/

# Node
node_modules/
npm-debug.log
package-lock.json

# IDE
.vscode/
.idea/
*.swp

# OS
.DS_Store
Thumbs.db
"""

ENV_TEMPLATE = """# Environment variables for Emo AI project
# Add your keys here
API_KEY=
SECRET_KEY=
DATABASE_URL=
"""


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------
class UndefinedNameVisitor(ast.NodeVisitor):
    """Collect names used before being defined in the current module."""

    def __init__(self) -> None:
        self.scopes: List[set[str]] = [set()]
        self.used: set[str] = set()

    @property
    def current_scope(self) -> set[str]:
        return self.scopes[-1]

    def define(self, name: str) -> None:
        self.current_scope.add(name)

    def is_defined(self, name: str) -> bool:
        return any(name in scope for scope in reversed(self.scopes))

    def _define_targets(self, target: ast.AST) -> None:
        if isinstance(target, ast.Name):
            self.define(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for item in target.elts:
                self._define_targets(item)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        self.define(node.name)
        self.scopes.append(set())
        for arg in node.args.args + node.args.kwonlyargs:
            self.define(arg.arg)
        if node.args.vararg:
            self.define(node.args.vararg.arg)
        if node.args.kwarg:
            self.define(node.args.kwarg.arg)
        self.generic_visit(node)
        self.scopes.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        self.visit_FunctionDef(node)  # type: ignore[arg-type]

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        self.define(node.name)
        self.scopes.append(set())
        self.generic_visit(node)
        self.scopes.pop()

    def visit_Assign(self, node: ast.Assign) -> Any:
        for target in node.targets:
            self._define_targets(target)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> Any:
        self._define_targets(node.target)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> Any:
        self._define_targets(node.target)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> Any:
        for alias in node.names:
            self.define(alias.asname or alias.name.split(".")[0])

    def visit_ImportFrom(self, node: ast.ImportFrom) -> Any:
        for alias in node.names:
            self.define(alias.asname or alias.name)

    def visit_Name(self, node: ast.Name) -> Any:
        if isinstance(node.ctx, ast.Load):
            if not self.is_defined(node.id) and node.id not in dir(builtins):
                self.used.add(node.id)
        self.generic_visit(node)


# ---------------------------------------------------------------------------
# 1) Auto debugger
# ---------------------------------------------------------------------------
class AutoDebugger(Tool):
    name = "auto_debugger"
    description = "Automatically detect and suggest fixes for code errors (syntax, runtime, logical)"
    category = "Project Intelligence"
    icon = "🐛"
    parameters = {"file_path": "string", "code": "string", "run_code": "boolean"}

    def run(self, file_path: str = "", code: str = "", run_code: bool = False) -> str:
        if file_path:
            try:
                path = _safe_path(Path(file_path), must_exist=True)
            except (ValueError, FileNotFoundError) as exc:
                return f"❌ {exc}"
            code = _read_text(path)
            suffix = path.suffix.lower()
        else:
            if not code:
                return "Please provide either file_path or code"
            suffix = ""

        issues: List[Dict[str, Any]] = []

        try:
            ast.parse(code)
        except SyntaxError as exc:
            issues.append(
                {
                    "type": "syntax",
                    "line": exc.lineno,
                    "offset": exc.offset,
                    "msg": str(exc),
                    "suggestion": self._suggest_syntax_fix(exc),
                }
            )

        if suffix == ".py":
            try:
                tree = ast.parse(code)
                visitor = UndefinedNameVisitor()
                visitor.visit(tree)
                for name in sorted(visitor.used):
                    issues.append(
                        {
                            "type": "undefined",
                            "line": 0,
                            "msg": f"Variable/function '{name}' may be undefined",
                            "suggestion": f"Define '{name}' before using it, or check for a typo/missing import.",
                        }
                    )
            except SyntaxError:
                pass

        if run_code and suffix == ".py":
            issues.extend(self._runtime_test(code))

        if not issues:
            return "✅ No issues detected. Code looks clean."

        lines = [f"🔍 Found {len(issues)} issue(s):", ""]
        for idx, issue in enumerate(issues, 1):
            lines.append(f"--- Issue {idx} ---")
            lines.append(f"Type: {issue.get('type', 'unknown')}")
            if issue.get("line"):
                lines.append(f"Line: {issue['line']}")
            if issue.get("offset"):
                lines.append(f"Offset: {issue['offset']}")
            lines.append(f"Message: {issue.get('msg', '')}")
            suggestion = issue.get("suggestion")
            if suggestion:
                lines.append(f"💡 Suggestion: {suggestion}")
            lines.append("")
        return "\n".join(lines).strip()

    def _runtime_test(self, code: str) -> List[Dict[str, Any]]:
        issues: List[Dict[str, Any]] = []
        tmp_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as handle:
                handle.write(code)
                tmp_path = Path(handle.name)

            result = subprocess.run(
                [sys.executable, "-I", str(tmp_path)],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode != 0:
                stderr = (result.stderr or result.stdout or "").strip()
                issues.append(
                    {
                        "type": "runtime",
                        "msg": stderr[:800] if stderr else "Process exited with an error.",
                        "suggestion": "Check exceptions, missing imports, and infinite loops.",
                    }
                )
        except subprocess.TimeoutExpired:
            issues.append(
                {
                    "type": "runtime",
                    "msg": "Execution timed out (10s) — possible infinite loop.",
                    "suggestion": "Add a break condition or optimize the loop.",
                }
            )
        except Exception as exc:
            issues.append(
                {
                    "type": "runtime",
                    "msg": str(exc),
                    "suggestion": "Ensure the code can run independently.",
                }
            )
        finally:
            if tmp_path and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
        return issues

    def _suggest_syntax_fix(self, exc: SyntaxError) -> str:
        message = str(exc).lower()
        if "unexpected indent" in message:
            return "Fix indentation and keep spaces/tabs consistent."
        if "missing parentheses" in message:
            return "Add the missing parentheses or brackets."
        if "invalid syntax" in message:
            return "Check for typos, missing colons, unmatched brackets, or invalid operators."
        return "Review the code near the reported line."


# ---------------------------------------------------------------------------
# 2) AI code reviewer
# ---------------------------------------------------------------------------
class AICodeReviewer(Tool):
    name = "ai_code_reviewer"
    description = "Use LLM to review code for quality, security, performance, and best practices"
    category = "Project Intelligence"
    icon = "🤖"
    parameters = {"file_path": "string", "code": "string", "language": "string", "focus": "string"}

    def __init__(self) -> None:
        super().__init__()
        self._brain: Optional[Any] = None

    def set_brain(self, brain: Any) -> None:
        self._brain = brain

    def run(self, file_path: str = "", code: str = "", language: str = "", focus: str = "all") -> str:
        if file_path:
            try:
                path = _safe_path(Path(file_path), must_exist=True)
            except (ValueError, FileNotFoundError) as exc:
                return f"❌ {exc}"
            code = _read_text(path)
            if not language:
                language = {
                    ".py": "python",
                    ".js": "javascript",
                    ".jsx": "javascript",
                    ".ts": "typescript",
                    ".tsx": "typescript",
                    ".html": "html",
                    ".css": "css",
                    ".json": "json",
                    ".md": "markdown",
                }.get(path.suffix.lower(), "code")
        elif not code:
            return "Please provide either file_path or code"

        if not self._brain or not BRAIN_AVAILABLE:
            return self._basic_review(code, language)

        focus_prompts = {
            "security": "Focus on security vulnerabilities: injection, XSS, unsafe deserialization, hardcoded secrets.",
            "performance": "Focus on performance issues: inefficient loops, memory leaks, blocking operations.",
            "style": "Focus on coding style, readability, naming conventions, and adherence to standards.",
            "bugs": "Focus on potential bugs: off-by-one, null references, unhandled exceptions, logic errors.",
            "all": "Cover all aspects: security, performance, bugs, style, and best practices.",
        }

        system = f"""You are an expert code reviewer. Analyze the provided {language} code.
{focus_prompts.get(focus, focus_prompts['all'])}

Provide a structured review with:
- Summary (1-2 sentences)
- Issues found (list with severity: Critical, High, Medium, Low)
- Suggestions for improvement
- Positive aspects (if any)

Be concise and actionable."""
        user = f"Code to review:\n```{language}\n{code[:8000]}\n```"

        try:
            return self._brain.ask(system=system, user=user, temperature=0.3, max_tokens=2000)
        except Exception as exc:
            return f"❌ AI review failed: {exc}\n\nBasic static review:\n{self._basic_review(code, language)}"

    def _basic_review(self, code: str, language: str) -> str:
        issues: List[str] = []
        lowered = code.lower()

        if "password" in lowered and "api_key" not in lowered and "secret" not in lowered:
            issues.append("⚠️ Potential hardcoded secret (password)")
        if "eval(" in code:
            issues.append("⚠️ Use of eval() — security risk")
        if "exec(" in code:
            issues.append("⚠️ Use of exec() — security risk")
        if "import *" in code and language == "python":
            issues.append("⚠️ Wildcard import (import *) — may cause namespace pollution")
        if len(code.splitlines()) > 500:
            issues.append("ℹ️ File is long (>500 lines). Consider splitting it into modules.")

        if issues:
            return "Basic static analysis found:\n" + "\n".join(issues)
        return "No obvious issues detected in static analysis."


# ---------------------------------------------------------------------------
# 3) Project execution monitor
# ---------------------------------------------------------------------------
@dataclass
class MonitorSession:
    session_id: str
    command: str
    cwd: Path
    process: subprocess.Popen
    logs: Deque[str] = field(default_factory=lambda: deque(maxlen=1000))
    restarts: int = 0
    stop_event: threading.Event = field(default_factory=threading.Event)
    reader_thread: Optional[threading.Thread] = None
    monitor_thread: Optional[threading.Thread] = None


class ProjectMonitor(Tool):
    name = "project_monitor"
    description = "Run a project and monitor logs, auto-restart on crash, provide live output"
    category = "Project Intelligence"
    icon = "📺"
    parameters = {"project_dir": "string", "command": "string", "watch_files": "boolean", "max_restarts": "number"}

    def __init__(self) -> None:
        super().__init__()
        self._sessions: Dict[str, MonitorSession] = {}
        self._lock = threading.RLock()

    def _safe_read_logs(self, session: MonitorSession) -> None:
        proc = session.process
        if not proc.stdout:
            return

        try:
            for line in iter(proc.stdout.readline, ""):
                if session.stop_event.is_set():
                    break
                text = line.rstrip("\n")
                with self._lock:
                    session.logs.append(text)
            with self._lock:
                session.logs.append("[MONITOR] output stream closed.")
        except Exception as exc:
            with self._lock:
                session.logs.append(f"[MONITOR] log reader error: {exc}")

    def _run_command_safe(self, command: str, cwd: Path) -> subprocess.Popen:
        if any(token in command for token in ("&&", "||", "|", ";", "`", "$(")):
            raise ValueError("Dangerous shell operator detected. Use a single command only.")

        parts = shlex.split(command)
        if not parts:
            raise ValueError("Empty command")

        if parts[0] not in ALLOWED_COMMANDS:
            raise ValueError(f"Command '{parts[0]}' not allowed. Allowed: {', '.join(sorted(ALLOWED_COMMANDS))}")

        return subprocess.Popen(
            parts,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            shell=False,
        )

    def _start_reader(self, session: MonitorSession) -> None:
        reader = threading.Thread(target=self._safe_read_logs, args=(session,), daemon=True)
        session.reader_thread = reader
        reader.start()

    def _monitor_loop(self, session_id: str, command: str, cwd: Path, max_restarts: int) -> None:
        while True:
            with self._lock:
                session = self._sessions.get(session_id)
            if not session or session.stop_event.is_set():
                break

            proc = session.process
            code = proc.poll()
            if code is None:
                time.sleep(1)
                continue

            if session.restarts >= max_restarts:
                with self._lock:
                    session.logs.append(f"[MONITOR] Process exited with code {code}. Restart limit reached.")
                    session.stop_event.set()
                break

            session.restarts += 1
            with self._lock:
                session.logs.append(
                    f"[MONITOR] Process exited with code {code}. Restarting ({session.restarts}/{max_restarts})..."
                )

            try:
                if proc.stdout:
                    try:
                        proc.stdout.close()
                    except OSError:
                        pass
                try:
                    proc.terminate()
                    proc.wait(timeout=3)
                except Exception:
                    pass

                new_proc = self._run_command_safe(command, cwd)
                session.process = new_proc
                self._start_reader(session)
            except Exception as exc:
                with self._lock:
                    session.logs.append(f"[MONITOR] Failed to restart: {exc}")
                    session.stop_event.set()
                break

        # cleanup is handled by stop_monitor or on exit
        self._cleanup_session(session_id, keep_logs=True)

    def _cleanup_session(self, session_id: str, *, keep_logs: bool = False) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return

            if not keep_logs:
                session.logs.clear()

            proc = session.process
            try:
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
            except Exception:
                pass

            if proc.stdout:
                try:
                    proc.stdout.close()
                except Exception:
                    pass

            if session.stop_event.is_set():
                self._sessions.pop(session_id, None)

    def run(
        self,
        project_dir: str = ".",
        command: str = "",
        watch_files: bool = True,
        max_restarts: int = 5,
    ) -> str:
        try:
            target = _safe_path(Path(project_dir))
        except ValueError as exc:
            return f"❌ {exc}"

        if not target.is_dir():
            return f"❌ Not a directory: {target}"

        if not command:
            if (target / "package.json").exists():
                command = "npm start"
            elif (target / "main.py").exists():
                command = f"{sys.executable} main.py"
            else:
                return "❌ Could not auto-detect a start command. Provide 'command'."

        try:
            process = self._run_command_safe(command, target)
        except Exception as exc:
            return f"❌ {exc}"

        session_id = str(uuid.uuid4())
        session = MonitorSession(session_id=session_id, command=command, cwd=target, process=process)

        with self._lock:
            self._sessions[session_id] = session

        self._start_reader(session)
        monitor = threading.Thread(
            target=self._monitor_loop,
            args=(session_id, command, target, max_restarts),
            daemon=True,
        )
        session.monitor_thread = monitor
        monitor.start()

        logger.info("Monitor started: %s for %s", session_id, target.name)
        return (
            f"✅ Project monitor started for {target.name}\n"
            f"Session ID: {session_id}\n"
            f"Command: {command}\n"
            f"Auto-restart limit: {max_restarts}\n"
            f"Use get_logs('{session_id}') to see output, stop_monitor('{session_id}') to stop."
        )

    def get_logs(self, session_id: str, lines: int = 50) -> str:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return f"❌ Session {session_id} not found."
            recent = list(session.logs)[-max(1, lines):]

        if not recent:
            return "No logs yet."
        return "\n".join(recent)

    def get_monitor_logs(self, session_id: str, lines: int = 50) -> str:
        return self.get_logs(session_id, lines)

    def stop_monitor(self, session_id: str) -> str:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return f"❌ Session {session_id} not active."
            session.stop_event.set()
            session.logs.append("[MONITOR] stopping...")

        self._cleanup_session(session_id, keep_logs=True)

        with self._lock:
            self._sessions.pop(session_id, None)

        logger.info("Monitor stopped: %s", session_id)
        return f"✅ Project monitor stopped for session {session_id}."

    def list_sessions(self) -> str:
        with self._lock:
            if not self._sessions:
                return "No active monitor sessions."
            lines = [
                f"{sid}: PID {session.process.pid}, restarts {session.restarts}"
                for sid, session in self._sessions.items()
            ]
        return "Active sessions:\n" + "\n".join(lines)


_monitor_lock = threading.Lock()
_monitor_instance: Optional[ProjectMonitor] = None


def get_monitor() -> ProjectMonitor:
    global _monitor_instance
    with _monitor_lock:
        if _monitor_instance is None:
            _monitor_instance = ProjectMonitor()
    return _monitor_instance


# ---------------------------------------------------------------------------
# 4) Project scaffold
# ---------------------------------------------------------------------------
class ProjectScaffold(Tool):
    name = "project_scaffold"
    description = "Generate a complete project structure from template (react, fastapi, html, node, python)"
    category = "Project Intelligence"
    icon = "🏗️"
    parameters = {
        "project_type": "string",
        "project_name": "string",
        "output_dir": "string",
        "init_git": "boolean",
    }

    def run(
        self,
        project_type: str = "python",
        project_name: str = "my-project",
        output_dir: str = "",
        init_git: bool = True,
    ) -> str:
        ptype = project_type.lower().strip()
        if ptype not in PROJECT_TEMPLATES:
            return f"❌ Unsupported project type: {ptype}. Available: {', '.join(PROJECT_TEMPLATES.keys())}"

        template = PROJECT_TEMPLATES[ptype]
        base = (Path(output_dir) / project_name) if output_dir else (Path.cwd() / project_name)

        try:
            base = _safe_path(base)
        except ValueError as exc:
            return f"❌ {exc}"

        if base.exists():
            return f"❌ Directory already exists: {base}. Remove it or choose another name."

        created: List[str] = []
        try:
            for rel_path, content in template["files"].items():
                fp = base / rel_path
                _write_text(fp, content)
                created.append(str(fp.relative_to(base)))

            _write_text(base / ".gitignore", GITIGNORE_CONTENT)
            created.append(".gitignore")

            _write_text(base / ".env", ENV_TEMPLATE)
            created.append(".env")

            if init_git:
                if _command_exists("git"):
                    _run_command(["git", "init"], base, timeout=20)
                    created.append("git repository initialized")
                else:
                    created.append("git not found; skipped initialization")
        except Exception as exc:
            return f"❌ Failed to create files: {exc}"

        files_text = "\n".join(f"  ├── {item}" for item in created)
        install_cmd = " ".join(template["install"]) if template["install"] else "No install step needed"
        run_cmd = install_cmd if template["install"] else "open ."

        return (
            f"✅ Project '{project_name}' ({ptype}) scaffolded at {base}\n"
            f"Files:\n{files_text}\n\n"
            f"📦 Install: {install_cmd}\n"
            f"🚀 Run: cd {base} && {run_cmd}"
        )


# ---------------------------------------------------------------------------
# 5) Project analyzer
# ---------------------------------------------------------------------------
class ProjectAnalyzer(Tool):
    name = "project_analyzer"
    description = "Analyze project structure, dependencies, and detect issues"
    category = "Project Intelligence"
    icon = "🔬"
    parameters = {"project_dir": "string"}

    def run(self, project_dir: str = ".") -> str:
        try:
            target = _safe_path(Path(project_dir), must_exist=True)
        except (ValueError, FileNotFoundError) as exc:
            return f"❌ {exc}"

        if not target.is_dir():
            return f"❌ Not a directory: {target}"

        info: Dict[str, Any] = {
            "path": str(target),
            "name": target.name,
            "files": 0,
            "dirs": 0,
            "total_size": 0,
            "languages": {},
            "dependencies": [],
            "issues": [],
        }

        skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", "env", "dist", "build"}

        for item in target.rglob("*"):
            if any(part in skip_dirs for part in item.parts):
                continue
            if _is_hidden_path(item.relative_to(target)):
                continue
            try:
                if item.is_file():
                    info["files"] += 1
                    info["total_size"] += item.stat().st_size
                    ext = item.suffix.lower()
                    if ext:
                        info["languages"][ext] = info["languages"].get(ext, 0) + 1
                elif item.is_dir():
                    info["dirs"] += 1
            except OSError:
                continue

        pkg_json = target / "package.json"
        if pkg_json.exists():
            try:
                pkg = json.loads(_read_text(pkg_json))
                deps = {}
                deps.update(pkg.get("dependencies", {}))
                deps.update(pkg.get("devDependencies", {}))
                info["dependencies"].extend([f"{k}@{v}" for k, v in list(deps.items())[:30]])
            except Exception:
                pass

        req_txt = target / "requirements.txt"
        if req_txt.exists():
            lines = [
                line.strip()
                for line in _read_text(req_txt).splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            ]
            info["dependencies"].extend(lines[:30])

        pyproject = target / "pyproject.toml"
        if pyproject.exists() and not info["dependencies"]:
            info["dependencies"].append("pyproject.toml detected (dependency parsing not expanded in this version)")

        if info["files"] == 0:
            info["issues"].append("Project is empty")
        if not (target / ".git").exists():
            info["issues"].append("Not a git repository (git init recommended)")

        lang_summary = ", ".join(
            f"{ext}: {count}" for ext, count in sorted(info["languages"].items(), key=lambda x: -x[1])[:10]
        ) or "None detected"
        dep_summary = "\n    ".join(info["dependencies"][:15]) if info["dependencies"] else "None detected"
        issue_summary = "\n  ".join(f"⚠️ {item}" for item in info["issues"]) if info["issues"] else "✅ None"

        return (
            f"📁 Project: {info['name']}\n"
            f"📍 Path: {info['path']}\n"
            f"📄 Files: {info['files']} | 📂 Dirs: {info['dirs']} | 💾 Size: {_fmt_size(info['total_size'])}\n"
            f"🔤 Languages: {lang_summary}\n"
            f"📦 Dependencies:\n    {dep_summary}\n"
            f"⚠️ Issues:\n  {issue_summary}"
        )


class FileReader(Tool):
    name = "file_reader"
    description = "Read the contents of a specific file in the project"
    category = "Project Intelligence"
    icon = "📄"
    parameters = {"file_path": "string", "max_lines": "number"}

    def run(self, file_path: str, max_lines: int = 100) -> str:
        try:
            target = _safe_path(Path(file_path), must_exist=True)
        except (ValueError, FileNotFoundError) as exc:
            return f"❌ {exc}"

        if not target.is_file():
            return f"❌ Not a file: {target}"

        try:
            content = _read_text(target)
            lines = content.splitlines()
            if len(lines) > max_lines:
                content = "\n".join(lines[:max_lines]) + f"\n... ({len(lines) - max_lines} more lines)"
            return f"📄 File: {target.name}\n📍 Path: {target}\n📏 Lines: {len(lines)}\n\n```\n{content}\n```"
        except Exception as e:
            return f"❌ Error reading file: {e}"


class DirectoryLister(Tool):
    name = "directory_lister"
    description = "List files and directories in a project folder"
    category = "Project Intelligence"
    icon = "📂"
    parameters = {"dir_path": "string", "recursive": "boolean", "max_depth": "number"}

    def run(self, dir_path: str = ".", recursive: bool = False, max_depth: int = 3) -> str:
        try:
            target = _safe_path(Path(dir_path), must_exist=True)
        except (ValueError, FileNotFoundError) as exc:
            return f"❌ {exc}"

        if not target.is_dir():
            return f"❌ Not a directory: {target}"

        skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", "env", "dist", "build"}
        result = []

        def list_dir(path: Path, current_depth: int = 0, prefix: str = ""):
            if current_depth >= max_depth:
                return
            try:
                items = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
                for i, item in enumerate(items):
                    if any(part in skip_dirs for part in item.parts):
                        continue
                    if _is_hidden_path(item.relative_to(target)):
                        continue
                    is_last = i == len(items) - 1
                    connector = "└── " if is_last else "├── "
                    result.append(f"{prefix}{connector}{item.name}{'/' if item.is_dir() else ''}")
                    if item.is_dir() and recursive:
                        extension = "    " if is_last else "│   "
                        list_dir(item, current_depth + 1, prefix + extension)
            except PermissionError:
                result.append(f"{prefix}└── [Permission denied]")

        result.append(f"📁 {target.name}/")
        list_dir(target)
        return "\n".join(result)


# ---------------------------------------------------------------------------
# 6) Dependency manager
# ---------------------------------------------------------------------------
class DependencyManager(Tool):
    name = "dependency_manager"
    description = "Install, add, or update project dependencies"
    category = "Project Intelligence"
    icon = "📦"
    parameters = {"action": "string", "package": "string", "project_dir": "string"}

    SAFE_PACKAGE_RE = re.compile(r"^[A-Za-z0-9@._\-/=<>!~\[\],:+*]+$")

    @staticmethod
    def _is_safe_package_spec(spec: str) -> bool:
        if not spec or spec.strip() != spec:
            return False
        if any(ch.isspace() for ch in spec):
            return False
        if any(token in spec for token in (";", "&", "|", "`", "$(", "\\", "\n", "\r")):
            return False
        return bool(DependencyManager.SAFE_PACKAGE_RE.fullmatch(spec))

    def run(self, action: str = "install", package: str = "", project_dir: str = ".") -> str:
        try:
            target = _safe_path(Path(project_dir), must_exist=True)
        except (ValueError, FileNotFoundError) as exc:
            return f"❌ {exc}"

        if not target.is_dir():
            return f"❌ Not a directory: {target}"

        has_npm = (target / "package.json").exists()
        has_pip = any((target / name).exists() for name in ("requirements.txt", "setup.py", "pyproject.toml"))

        if not has_npm and not has_pip:
            return "❌ No recognized package manager (package.json, requirements.txt, setup.py, pyproject.toml)"

        action = action.lower().strip()
        package = package.strip()

        if has_npm:
            if not _command_exists("npm"):
                return "❌ npm is not installed or not in PATH"

            if action == "install" and not package:
                cmd = ["npm", "install"]
            elif action == "add" and package:
                if not self._is_safe_package_spec(package):
                    return "❌ Invalid npm package spec"
                cmd = ["npm", "install", package]
            elif action == "remove" and package:
                if not self._is_safe_package_spec(package):
                    return "❌ Invalid npm package spec"
                cmd = ["npm", "uninstall", package]
            elif action == "update":
                cmd = ["npm", "update"]
            else:
                return f"❌ Unknown npm action: {action} (or missing package name)"

            try:
                result = _run_command(cmd, target, timeout=120)
                if result.returncode != 0:
                    return f"❌ npm {action} failed:\n{(result.stderr or result.stdout)[:800]}"
                return f"✅ npm {action} completed successfully\n{(result.stdout or '')[:1000]}"
            except subprocess.TimeoutExpired:
                return f"❌ npm {action} timed out"
            except Exception as exc:
                return f"❌ npm {action} error: {exc}"

        python_exe = sys.executable
        if action == "install" and not package:
            req_file = target / "requirements.txt"
            if not req_file.exists():
                return "❌ requirements.txt not found. Create one first."
            cmd = [python_exe, "-m", "pip", "install", "-r", str(req_file)]
        elif action == "add" and package:
            if not self._is_safe_package_spec(package):
                return "❌ Invalid pip package spec"
            cmd = [python_exe, "-m", "pip", "install", package]
        elif action == "remove" and package:
            if not self._is_safe_package_spec(package):
                return "❌ Invalid pip package spec"
            cmd = [python_exe, "-m", "pip", "uninstall", package, "-y"]
        else:
            return f"❌ Unknown pip action: {action} (or missing package name)"

        try:
            result = _run_command(cmd, target, timeout=120)
            if result.returncode != 0:
                return f"❌ pip {action} failed:\n{(result.stderr or result.stdout)[:800]}"

            if action == "add" and package:
                req_file = target / "requirements.txt"
                if req_file.exists():
                    freeze = _run_command([python_exe, "-m", "pip", "freeze"], target, timeout=30)
                    if freeze.returncode == 0:
                        exact_match = None
                        for line in freeze.stdout.splitlines():
                            if line.lower().startswith(package.split("==")[0].lower() + "=="):
                                exact_match = line.strip()
                                break
                        if exact_match:
                            existing = req_file.read_text(encoding="utf-8", errors="replace").splitlines()
                            if exact_match not in existing:
                                req_file.write_text("\n".join(existing + [exact_match]) + "\n", encoding="utf-8")

            return f"✅ pip {action} completed successfully\n{(result.stdout or '')[:1000]}"
        except subprocess.TimeoutExpired:
            return f"❌ pip {action} timed out"
        except Exception as exc:
            return f"❌ pip {action} error: {exc}"


# ---------------------------------------------------------------------------
# 7) Codebase refactor
# ---------------------------------------------------------------------------
class CodebaseRefactor(Tool):
    name = "codebase_refactor"
    description = "Reorganize project structure (move files into src/, tests/, docs/ etc.)"
    category = "Project Intelligence"
    icon = "🔨"
    parameters = {"project_dir": "string", "structure": "string", "dry_run": "boolean"}

    def run(self, project_dir: str = ".", structure: str = "", dry_run: bool = False) -> str:
        try:
            target = _safe_path(Path(project_dir), must_exist=True)
        except (ValueError, FileNotFoundError) as exc:
            return f"❌ {exc}"

        if not target.is_dir():
            return f"❌ Not a directory: {target}"

        dir_map = {
            "src": {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java"},
            "tests": {"test_*.py", "*_test.py", "*.test.js", "*.spec.js"},
            "docs": {".md", ".rst", ".txt"},
            "config": {".json", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".conf"},
        }
        exclude = {"node_modules", "__pycache__", ".git", ".venv", "venv", "env", "dist", "build", ".env"}

        plan: List[Tuple[Path, Path]] = []

        for root, dirs, files in os.walk(target):
            dirs[:] = [d for d in dirs if d not in exclude]
            root_path = Path(root)
            rel_root = root_path.relative_to(target)
            if any(part in exclude for part in rel_root.parts):
                continue

            for name in files:
                src = root_path / name
                if any(part in exclude for part in src.relative_to(target).parts):
                    continue

                category = None
                lower_name = name.lower()
                ext = src.suffix.lower()

                if ext in dir_map["src"]:
                    category = "src"
                elif ext in dir_map["docs"]:
                    category = "docs"
                elif ext in dir_map["config"]:
                    category = "config"
                elif (
                    lower_name.startswith("test_")
                    or lower_name.endswith("_test.py")
                    or ".test." in lower_name
                    or ".spec." in lower_name
                ):
                    category = "tests"

                if not category:
                    continue

                if src.relative_to(target).parts[:1] == (category,):
                    continue

                dst = target / category / src.relative_to(target)
                plan.append((src, dst))

        if dry_run:
            if not plan:
                return "✅ Dry run: no files need moving (already organized)"
            lines = ["📋 Dry run – files that would be moved:"]
            for src, dst in plan:
                lines.append(f"  {src.relative_to(target)} → {dst.relative_to(target)}")
            return "\n".join(lines)

        moved: List[str] = []
        for src, dst in plan:
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                final_dst = _unique_destination(dst)
                shutil.move(str(src), str(final_dst))
                moved.append(f"{src.relative_to(target)} → {final_dst.relative_to(target)}")
            except Exception as exc:
                return f"❌ Failed to move {src.name}: {exc}"

        if not moved:
            return "✅ Already well-organized — no changes needed"

        return "✅ Reorganized:\n  " + "\n  ".join(moved)


# ---------------------------------------------------------------------------
# 8) Deployment builder
# ---------------------------------------------------------------------------
class DeploymentBuilder(Tool):
    name = "deployment_builder"
    description = "Generate deployment configuration (Vercel, Docker, Firebase, GitHub Actions)"
    category = "Project Intelligence"
    icon = "🚀"
    parameters = {"project_dir": "string", "target": "string", "framework": "string"}

    def run(self, project_dir: str = ".", target: str = "vercel", framework: str = "") -> str:
        try:
            base = _safe_path(Path(project_dir), must_exist=True)
        except (ValueError, FileNotFoundError) as exc:
            return f"❌ {exc}"

        if not base.is_dir():
            return f"❌ Not a directory: {base}"

        target = target.lower().strip()
        created_files: List[str] = []
        instructions: List[str] = []

        try:
            if target == "vercel":
                vc_file = base / "vercel.json"
                if not framework:
                    if (base / "next.config.js").exists():
                        framework = "nextjs"
                    elif (base / "package.json").exists() and (base / "src/App.js").exists():
                        framework = "create-react-app"
                    else:
                        framework = "other"

                vc_config = {
                    "version": 2,
                    "framework": framework,
                    "routes": [{"src": "/(.*)", "dest": "/"}],
                }
                _write_text(vc_file, json.dumps(vc_config, indent=2))
                created_files.append("vercel.json")
                instructions.append("Run: npx vercel --prod (after installing Vercel CLI)")

            elif target == "docker":
                dockerfile = base / "Dockerfile"
                if not dockerfile.exists():
                    if (base / "requirements.txt").exists():
                        dockerfile_content = """FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -r requirements.txt
EXPOSE 8000
CMD ["python", "main.py"]
"""
                    elif (base / "package.json").exists():
                        dockerfile_content = """FROM node:18-alpine
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
EXPOSE 3000
CMD ["npm", "start"]
"""
                    else:
                        dockerfile_content = """FROM alpine:latest
WORKDIR /app
COPY . .
CMD ["echo", "No specific runtime detected"]
"""
                    _write_text(dockerfile, dockerfile_content)
                    created_files.append("Dockerfile")

                compose = base / "docker-compose.yml"
                if not compose.exists():
                    compose_content = """version: '3.8'
services:
  app:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - .:/app
"""
                    _write_text(compose, compose_content)
                    created_files.append("docker-compose.yml")
                instructions.append("Run: docker-compose up --build")

            elif target == "firebase":
                fb_file = base / "firebase.json"
                fb_config = {
                    "hosting": {
                        "public": "public",
                        "ignore": ["firebase.json", "**/.*", "**/node_modules/**"],
                        "rewrites": [{"source": "**", "destination": "/index.html"}],
                    }
                }
                _write_text(fb_file, json.dumps(fb_config, indent=2))
                created_files.append("firebase.json")
                instructions.append("Run: firebase deploy (after installing Firebase CLI)")

            elif target == "github-actions":
                ga_dir = base / ".github" / "workflows"
                ga_dir.mkdir(parents=True, exist_ok=True)
                yml_file = ga_dir / "deploy.yml"
                yml_content = """name: Deploy

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '18'
      - run: npm ci
      - run: npm run build
      # Add your deploy steps here
"""
                _write_text(yml_file, yml_content)
                created_files.append(".github/workflows/deploy.yml")
                instructions.append("Push to GitHub to trigger CI/CD")

            else:
                return f"❌ Unsupported target: {target}. Choose: vercel, docker, firebase, github-actions"
        except Exception as exc:
            return f"❌ Failed to generate deployment config: {exc}"

        file_lines = "\n  ".join(f"📄 {item}" for item in created_files) if created_files else "None"
        step_lines = "\n  ".join(f"➡ {item}" for item in instructions) if instructions else "None"

        return (
            f"✅ Deployment config for {target} generated:\n"
            f"  {file_lines}\n\n"
            f"📋 Next steps:\n"
            f"  {step_lines}"
        )


__all__ = [
    "AutoDebugger",
    "AICodeReviewer",
    "ProjectMonitor",
    "ProjectScaffold",
    "ProjectAnalyzer",
    "DependencyManager",
    "CodebaseRefactor",
    "DeploymentBuilder",
    "get_monitor",
]
