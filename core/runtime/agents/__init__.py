"""Phase G — Agent lifecycle and runtime package.

Exports AgentLifecycleManager for agent registration, state transitions,
heartbeat monitoring, and deregistration.
"""

from core.runtime.agents.agent_lifecycle import AgentLifecycleManager

__all__ = ["AgentLifecycleManager"]
