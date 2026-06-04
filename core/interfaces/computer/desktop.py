from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class IDesktopWorker(Protocol):
    """Protocol for desktop automation workers.

    LAW 1: Conforms to IDesktopWorker interface.
    LAW 10: External workers are unreliable — all calls MUST be guarded.
    RULE 2: All IO is isolated — no shared desktop state.
    """

    def launch_app(self, app_path: str, args: Optional[List[str]] = None) -> str:
        """Launch a desktop application.

        Args:
            app_path: Path to the application executable.
            args: Optional command-line arguments.

        Returns:
            Window handle string identifying the application instance.
        """
        ...

    def send_keys(self, text: str, window_handle: Optional[str] = None) -> bool:
        """Send keystrokes to the active or specified window.

        Args:
            text: Text or key sequence to send.
            window_handle: Optional target window handle.

        Returns:
            True if keys were sent successfully.
        """
        ...

    def mouse_move(self, x: int, y: int, window_handle: Optional[str] = None) -> bool:
        """Move the mouse cursor to screen coordinates.

        Args:
            x: Target X coordinate.
            y: Target Y coordinate.
            window_handle: Optional target window for relative coordinates.

        Returns:
            True if cursor was moved.
        """
        ...

    def capture_screen(self, region: Optional[Dict[str, int]] = None) -> bytes:
        """Capture a screenshot of the screen or a region.

        Args:
            region: Optional dict with x, y, width, height.

        Returns:
            Raw PNG image bytes.
        """
        ...

    def terminate(self, window_handle: Optional[str] = None) -> None:
        """Terminate the desktop session or specified app.

        Args:
            window_handle: Optional handle to terminate a specific app.
                           If None, terminates all managed apps.
        """
        ...
