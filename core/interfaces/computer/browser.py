from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class IBrowserWorker(Protocol):
    """Protocol for browser automation workers.

    LAW 1: Conforms to IBrowserWorker interface.
    LAW 10: External workers are unreliable — all calls MUST be guarded.
    RULE 2: All IO is isolated — no shared browser state.
    """

    def launch(self, url: Optional[str] = None, options: Optional[Dict[str, Any]] = None) -> str:
        """Launch a browser session.

        Args:
            url: Optional initial URL to navigate to.
            options: Browser launch options (headless, viewport, etc.).

        Returns:
            Session token string identifying the browser instance.
        """
        ...

    def navigate(self, url: str, timeout_sec: float = 30.0) -> bool:
        """Navigate the browser to a URL.

        Args:
            url: The target URL.
            timeout_sec: Maximum wait time for page load.

        Returns:
            True if navigation completed within timeout.
        """
        ...

    def click(self, selector: str, wait_sec: float = 5.0) -> bool:
        """Click an element identified by CSS/XPath selector.

        Args:
            selector: CSS selector or XPath expression.
            wait_sec: Maximum wait time for element visibility.

        Returns:
            True if click was successful.
        """
        ...

    def extract_dom(self, selector: Optional[str] = None) -> str:
        """Extract DOM content as HTML/structured text.

        Args:
            selector: Optional CSS selector to scope extraction.

        Returns:
            Extracted DOM content as string.
        """
        ...

    def close(self) -> None:
        """Close the browser session and release resources."""
        ...
