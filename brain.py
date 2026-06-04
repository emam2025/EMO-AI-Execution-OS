import os
import time
from typing import Dict, List, Optional, Tuple

from openai import OpenAI, AsyncOpenAI
import httpx

from core.security.keychain_provider import KeychainProvider


class Brain:
    """LLM interface supporting multiple providers.

    Supported providers:
    - openrouter: OpenRouter API (multi-model gateway)
    - groq: Groq API (fast inference)
    - gemini: Google Gemini API
    - ollama: Local Ollama instance (http://localhost:11434)

    Provider is selected via LLM_PROVIDER env var.
    API keys are loaded from OS Keychain (KeychainProvider) with
    env var fallback for development only.
    """

    PROVIDERS = {
        "openrouter": {
            "base_url": "https://openrouter.ai/api/v1",
            "default_model": "meta-llama/llama-3.3-70b-instruct",
        },
        "groq": {
            "base_url": "https://api.groq.com/openai/v1",
            "default_model": "llama-3.3-70b-versatile",
        },
        "gemini": {
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
            "default_model": "gemini-2.5-flash",
        },
        "ollama": {
            "base_url": "http://localhost:11434/v1",
            "api_key_env": "",
            "default_model": "llama3.2",
        },
    }

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        self.provider = provider or os.getenv("LLM_PROVIDER", "openrouter")
        self.model = model or os.getenv("LLM_MODEL", "")

        if self.provider not in self.PROVIDERS:
            raise ValueError(f"Unknown provider: {self.provider}. Choose from {list(self.PROVIDERS.keys())}")

        config = self.PROVIDERS[self.provider]

        if not self.model:
            self.model = config["default_model"]

        # API key priority: parameter > Keychain > env var
        if api_key:
            resolved_key = api_key
        elif self.provider == "ollama":
            resolved_key = "ollama"
        else:
            kp = KeychainProvider()
            resolved_key = kp.get(self.provider) or ""
            if not resolved_key:
                resolved_key = os.getenv(f"{self.provider.upper()}_API_KEY", "")
            if not resolved_key:
                resolved_key = "placeholder-key-not-configured"

        self._client = OpenAI(
            base_url=config["base_url"],
            api_key=resolved_key,
        )

        self._async_client = AsyncOpenAI(
            base_url=config["base_url"],
            api_key=resolved_key,
        )

    def ask(
        self,
        system: str = "",
        user: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        messages: Optional[List[Dict[str, str]]] = None,
        **kwargs,
    ) -> str:
        """Send a chat completion request to the LLM.

        Args:
            system: System prompt (optional).
            user: User message (required if messages not provided).
            temperature: Sampling temperature (0.0-2.0).
            max_tokens: Maximum tokens in response.
            messages: Full conversation history (optional, overrides user).
            **kwargs: Additional arguments passed to the API.

        Returns:
            str: The LLM's response text.
        """
        if messages is not None:
            final_messages = messages
            if system:
                # Insert system message at the beginning
                final_messages = [{"role": "system", "content": system}] + [
                    m for m in messages if m.get("role") != "system"
                ]
        else:
            final_messages: List[Dict[str, str]] = []
            if system:
                final_messages.append({"role": "system", "content": system})
            final_messages.append({"role": "user", "content": user})

        response = self._client.chat.completions.create(
            model=self.model,
            messages=final_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

        return response.choices[0].message.content or ""

    async def ask_async(
        self,
        system: str = "",
        user: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2048,
        messages: Optional[List[Dict[str, str]]] = None,
        **kwargs,
    ) -> str:
        """Async version of ask()."""
        if messages is not None:
            final_messages = messages
            if system:
                final_messages = [{"role": "system", "content": system}] + [
                    m for m in messages if m.get("role") != "system"
                ]
        else:
            final_messages: List[Dict[str, str]] = []
            if system:
                final_messages.append({"role": "system", "content": system})
            final_messages.append({"role": "user", "content": user})

        response = await self._async_client.chat.completions.create(
            model=self.model,
            messages=final_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

        return response.choices[0].message.content or ""

    def test_connection(self) -> Tuple[bool, str]:
        """Test the LLM connection.

        Returns:
            Tuple of (success: bool, model_name: str).
        """
        try:
            start = time.time()
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Reply with OK"}],
                max_tokens=5,
                temperature=0.0,
            )
            latency_ms = int((time.time() - start) * 1000)
            content = response.choices[0].message.content or ""
            return True, f"{self.model} ({latency_ms}ms)"
        except Exception as e:
            return False, str(e)

    def get_info(self) -> Dict:
        """Return provider and model info."""
        return {
            "provider": self.provider,
            "model": self.model,
            "base_url": self.PROVIDERS[self.provider]["base_url"],
        }
