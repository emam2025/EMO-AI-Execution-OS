import json
import sqlite3
from pathlib import Path
from core.tool_executor import create_full_registry, ToolRegistry
from memory import Memory
from brain import Brain
from agent import create_agents, Agent
from core.task_manager import AsyncTaskManager


def _load_agents_from_db_sync() -> dict:
    """Synchronous DB read to populate initial agents (runs on startup)."""
    db_path = "emo_ai.db"
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.execute("SELECT * FROM agents ORDER BY is_built_in DESC, name ASC")
        rows = cur.fetchall()
        conn.close()
        result = {}
        for row in rows:
            tools_list = json.loads(row["tools"] or "[]")
            mb = json.loads(row["model_binding"] or "{}")
            model_str = mb.get("model", "meta-llama/llama-3.3-70b-instruct")
            provider = mb.get("provider", "openrouter")
            system = row["system_prompt"] or ""
            result[row["name"]] = Agent(
                name=row["name"],
                brain=Brain(provider=provider, model=model_str),
                tools=None,  # tool registry is shared via state.tools
                system_instructions=system,
            )
        return result
    except Exception:
        return {}


class AppState:
    def __init__(self):
        self.tools: ToolRegistry = create_full_registry()
        self.memory = Memory()
        self.task_manager = AsyncTaskManager()
        # Load agents from DB (seeded on first run)
        self.agents = _load_agents_from_db_sync()
        if not self.agents:
            # Fallback to hardcoded if DB not yet seeded
            self.agents = create_agents(tools=self.tools)
        self.conversations = {}
        self.active_conversation_id = None

    def get_brain(self) -> Brain:
        return Brain()

    def reload_agents(self) -> None:
        """Reload agents from DB (called after CRUD operations)."""
        loaded = _load_agents_from_db_sync()
        if loaded:
            self.agents = loaded

    def get_agent_by_id(self, agent_id: str):
        """Look up an agent by id (returns Agent instance or None)."""
        return self.agents.get(agent_id)


state = AppState()
