from typing import Dict, List, Optional
from brain import Brain
from core.tool_executor import ToolRegistry


class Agent:
    """An AI agent with a specific role, LLM brain, and optional tools.

    Each agent has:
    - name: unique identifier
    - role: human-readable role description
    - brain: LLM interface for generating responses
    - tools: optional tool registry the agent can use
    - system_prompt: default system instructions
    """

    SYSTEM_PROMPTS = {
        "planner": (
            "You are a task planner and distributor. "
            "Analyze the user's request and break it down into actionable steps. "
            "Be concise and structured. "
            "CRITICAL RULES:\n"
            "1. NEVER list available tools as project contents or files.\n"
            "2. NEVER invent, hallucinate, or make up file names, directory structures, or project contents.\n"
            "3. If the user asks about their project and you have project analysis data, use ONLY that data.\n"
            "4. If you don't have project analysis data, say 'I need to analyze your project first' and stop.\n"
            "5. Available tools are CAPABILITIES you have, NOT the user's project files."
        ),
        "coder": (
            "You are an expert software engineer. "
            "Write clean, professional, well-documented code. "
            "Follow best practices and explain your decisions."
        ),
        "writer": (
            "You are a professional writer and content creator. "
            "Write clear, engaging, and well-structured content. "
            "Adapt your tone to the context."
        ),
        "researcher": (
            "You are a research analyst. "
            "Provide thorough, fact-based analysis with citations where possible. "
            "Be objective and comprehensive."
        ),
    }

    def __init__(
        self,
        name: str,
        brain: Optional[Brain] = None,
        tools: Optional[ToolRegistry] = None,
        system_instructions: str = "",
    ):
        self.name = name
        self.brain = brain or Brain()
        self.tools = tools
        self.system_instructions = system_instructions
        base_prompt = self.SYSTEM_PROMPTS.get(name, "")
        self.system_prompt = f"{system_instructions}\n\n{base_prompt}" if system_instructions else base_prompt

    def run(
        self,
        message: str,
        system: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        conversation_messages: Optional[List[Dict]] = None,
    ) -> str:
        """Execute the agent's task.

        Args:
            message: The task/message to process.
            system: Override system prompt (optional).
            temperature: LLM temperature.
            max_tokens: Maximum response tokens.
            conversation_messages: Previous conversation messages for context.

        Returns:
            str: The agent's response.
        """
        sys_prompt = system or self.system_prompt

        if self.tools:
            tool_list = self.tools.to_list()
            tool_names = [t["name"] for t in tool_list]
            sys_prompt += (
                f"\n\nAVAILABLE TOOLS (these are your CAPABILITIES, NOT project files):\n"
                f"{', '.join(tool_names)}.\n"
                f"CRITICAL: Never list these as project contents. Never invent file names or directories."
            )

        # Build messages with conversation history
        messages = None
        if conversation_messages:
            messages = []
            # Keep only recent messages to avoid token explosion (last 12)
            recent = conversation_messages[-12:]
            for msg in recent:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if content:
                    # Truncate very long messages
                    if len(content) > 1500:
                        content = content[:1500] + "..."
                    messages.append({"role": role, "content": content})
            # Add current message
            messages.append({"role": "user", "content": message})

        return self.brain.ask(
            system=sys_prompt,
            user=message,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def run_async(
        self,
        message: str,
        system: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        conversation_messages: Optional[List[Dict]] = None,
    ) -> str:
        """Async version of run()."""
        sys_prompt = system or self.system_prompt

        if self.tools:
            tool_list = self.tools.to_list()
            tool_names = [t["name"] for t in tool_list]
            sys_prompt += (
                f"\n\nAVAILABLE TOOLS (these are your CAPABILITIES, NOT project files):\n"
                f"{', '.join(tool_names)}.\n"
                f"CRITICAL: Never list these as project contents. Never invent file names or directories."
            )

        # Build messages with conversation history
        messages = None
        if conversation_messages:
            messages = []
            # Keep only recent messages to avoid token explosion (last 12)
            recent = conversation_messages[-12:]
            for msg in recent:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if content:
                    # Truncate very long messages
                    if len(content) > 1500:
                        content = content[:1500] + "..."
                    messages.append({"role": role, "content": content})
            # Add current message
            messages.append({"role": "user", "content": message})

        return await self.brain.ask_async(
            system=sys_prompt,
            user=message,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def execute_tool(self, tool_name: str, **kwargs) -> str:
        """Execute a tool through the agent's tool registry.

        Args:
            tool_name: Name of the tool to execute.
            **kwargs: Parameters for the tool.

        Returns:
            str: Tool result or error message.
        """
        if not self.tools:
            return f"Error: No tools available for agent '{self.name}'"
        return self.tools.execute(tool_name, **kwargs)


def create_agents(
    tools: Optional[ToolRegistry] = None,
    brain: Optional[Brain] = None,
    system_instructions: str = "",
) -> Dict[str, Agent]:
    """Create the default set of agents.

    Args:
        tools: Tool registry to share with agents.
        brain: Brain instance to share with agents.
        system_instructions: Global system instructions to prepend to each agent.

    Returns:
        Dict mapping agent names to Agent instances.
    """
    return {
        "planner": Agent("planner", brain=brain, tools=tools, system_instructions=system_instructions),
        "coder": Agent("coder", brain=brain, tools=tools, system_instructions=system_instructions),
        "writer": Agent("writer", brain=brain, tools=tools, system_instructions=system_instructions),
        "researcher": Agent("researcher", brain=brain, tools=tools, system_instructions=system_instructions),
    }
