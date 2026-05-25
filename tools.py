from abc import ABC, abstractmethod
from typing import Dict, List, Optional


class Tool(ABC):
    """Base class for all EMO AI tools.

    Every tool must implement:
    - name: unique identifier
    - description: human-readable description
    - category: tool category (DevOps, GitHub, etc.)
    - icon: emoji or symbol for UI display
    - parameters: dict of parameter_name -> type description
    - run(**kwargs): the actual execution logic
    """

    name: str = ""
    description: str = ""
    category: str = ""
    icon: str = ""
    parameters: Dict[str, str] = {}

    @abstractmethod
    def run(self, **kwargs) -> str:
        """Execute the tool with the given parameters.

        Returns:
            str: Human-readable result or error message.
        """
        pass

    def to_dict(self) -> Dict:
        """Serialize tool metadata for the UI."""
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "icon": self.icon,
            "parameters": self.parameters,
        }


class Registry:
    """Tool registry that categorizes and provides access to tools."""

    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool instance."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_all(self) -> List[Tool]:
        """List all registered tools."""
        return list(self._tools.values())

    def list_by_category(self, category: str) -> List[Tool]:
        """List tools in a specific category."""
        return [t for t in self._tools.values() if t.category == category]

    def categories(self) -> Dict[str, List[str]]:
        """Return categorized tool names."""
        result: Dict[str, List[str]] = {}
        for tool in self._tools.values():
            result.setdefault(tool.category, []).append(tool.name)
        return result


def create_registry() -> Registry:
    """Create and return an empty tool registry."""
    return Registry()
