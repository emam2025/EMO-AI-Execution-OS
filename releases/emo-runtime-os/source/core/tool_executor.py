"""Tool executor and registry for EMO AI agents.

This module provides:
- ToolRegistry: centralized registry for all tools
- ToolExecutor: executes tools with parameter validation
- Tool discovery and categorization
"""

import importlib
import inspect
import logging
from typing import Dict, List, Optional, Type

from tools import Tool, Registry

logger = logging.getLogger("emo-tools")


class ToolRegistry(Registry):
    """Extended registry with auto-discovery and execution."""

    def __init__(self):
        super().__init__()
        self._tool_classes: Dict[str, Type[Tool]] = {}

    def register_class(self, tool_class: Type[Tool]) -> None:
        """Register a tool class (instantiates it automatically)."""
        if not inspect.isclass(tool_class) or not issubclass(tool_class, Tool):
            raise TypeError(f"{tool_class} is not a Tool subclass")
        instance = tool_class()
        self._tools[instance.name] = instance
        self._tool_classes[instance.name] = tool_class

    def execute(self, tool_name: str, **kwargs) -> str:
        """Execute a tool by name with the given parameters.

        Args:
            tool_name: The name of the tool to execute.
            **kwargs: Parameters to pass to the tool's run method.

        Returns:
            str: The tool's result or error message.
        """
        tool = self.get(tool_name)
        if not tool:
            return f"Error: Tool '{tool_name}' not found"
        try:
            return tool.run(**kwargs)
        except Exception as e:
            logger.error(f"Tool execution error [{tool_name}]: {e}")
            return f"Error executing '{tool_name}': {str(e)}"

    def discover_tools(self, module_names: List[str]) -> int:
        """Auto-discover and register tools from modules.

        Args:
            module_names: List of module names to scan for Tool subclasses.

        Returns:
            int: Number of tools registered.
        """
        count = 0
        for module_name in module_names:
            try:
                module = importlib.import_module(module_name)
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(obj, Tool) and obj != Tool and obj.name:
                        self.register_class(obj)
                        count += 1
                        logger.info(f"Registered tool: {obj.name}")
            except ImportError as e:
                logger.warning(f"Failed to import module {module_name}: {e}")
            except Exception as e:
                logger.error(f"Error scanning module {module_name}: {e}")
        return count

    def search(self, query: str) -> List[Tool]:
        """Search tools by name or description.

        Args:
            query: Search query.

        Returns:
            List[Tool]: Matching tools.
        """
        query_lower = query.lower()
        results = []
        for tool in self._tools.values():
            if query_lower in tool.name.lower() or query_lower in tool.description.lower():
                results.append(tool)
        return results

    def to_list(self) -> List[Dict]:
        """Serialize all tools for the UI.

        Returns:
            List[Dict]: List of tool metadata dicts.
        """
        return [tool.to_dict() for tool in self._tools.values()]


def create_full_registry() -> ToolRegistry:
    """Create a registry with all available tools.

    Returns:
        ToolRegistry: Populated registry.
    """
    registry = ToolRegistry()

    modules_to_scan = [
        "project_tools",
        "devops_tools",
        "supabase_tools",
        "firebase_tools",
        "github_tools",
    ]

    count = registry.discover_tools(modules_to_scan)
    logger.info(f"Discovered {count} tools")
    return registry
