import json
from pathlib import Path
from core.tool_executor import create_full_registry, ToolRegistry
from memory import Memory
from brain import Brain
from agent import create_agents
from core.task_manager import AsyncTaskManager


class AppState:
    def __init__(self):
        self.tools: ToolRegistry = create_full_registry()
        self.memory = Memory()
        # Use the async-friendly task manager as the application state.
        # For sync compatibility, TaskManager shim remains available in the module.
        self.task_manager = AsyncTaskManager()
        self.agents = create_agents(tools=self.tools)
        self.conversations = {}
        self.active_conversation_id = None

    def get_brain(self) -> Brain:
        return Brain()

    def reload_agents(self) -> None:
        """Reload agents with updated system instructions from settings."""
        system_instructions = ""
        settings_file = Path(".emo_settings.json")
        if settings_file.exists():
            try:
                settings = json.loads(settings_file.read_text())
                system_instructions = settings.get("system_instructions", "")
            except Exception:
                pass
        brain = Brain()
        self.agents = create_agents(tools=self.tools, brain=brain, system_instructions=system_instructions)


state = AppState()
