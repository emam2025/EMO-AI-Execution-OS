"""ComputerWorkerStub — Safe mock implementing all 3 protocols.

Used for testing and development. No real browser, desktop, or
vision automation — pure deterministic stub responses.

CORE FREEZE: Zero import of playwright, selenium, pyautogui, opencv, PIL.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional


class ComputerWorkerStub:
    """Stub implementation of IBrowserWorker, IDesktopWorker, IVisionWorker.

    All methods return deterministic mock responses. No external
    dependencies required. Safe for CI/test environments.
    """

    def __init__(self) -> None:
        self._sessions: Dict[str, Dict[str, Any]] = {}

    # ── IBrowserWorker ─────────────────────────────────────────

    def launch(self, url: Optional[str] = None, options: Optional[Dict[str, Any]] = None) -> str:
        token = uuid.uuid4().hex[:16]
        self._sessions[token] = {"type": "browser", "url": url, "options": options or {}}
        return token

    def navigate(self, url: str, timeout_sec: float = 30.0) -> bool:
        return True

    def click(self, selector: str, wait_sec: float = 5.0) -> bool:
        return True

    def extract_dom(self, selector: Optional[str] = None) -> str:
        return "<html><body><p>Stub DOM content</p></body></html>"

    def close(self) -> None:
        self._sessions.clear()

    # ── IDesktopWorker ─────────────────────────────────────────

    def launch_app(self, app_path: str, args: Optional[List[str]] = None) -> str:
        handle = uuid.uuid4().hex[:16]
        self._sessions[handle] = {"type": "desktop", "app": app_path, "args": args or []}
        return handle

    def send_keys(self, text: str, window_handle: Optional[str] = None) -> bool:
        return True

    def mouse_move(self, x: int, y: int, window_handle: Optional[str] = None) -> bool:
        return True

    def capture_screen(self, region: Optional[Dict[str, int]] = None) -> bytes:
        return b"stub_screenshot_png_data"

    def terminate(self, window_handle: Optional[str] = None) -> None:
        pass

    # ── IVisionWorker ──────────────────────────────────────────

    def analyze_image(self, image_data: bytes, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return {"labels": ["stub_label"], "confidence": 0.95, "regions": []}

    def detect_ui_elements(self, image_data: bytes) -> List[Dict[str, Any]]:
        return [
            {
                "type": "button",
                "bounding_box": {"x": 10, "y": 10, "width": 100, "height": 30},
                "confidence": 0.92,
                "text": "Submit",
            }
        ]

    def ocr_text(self, image_data: bytes, languages: Optional[List[str]] = None) -> str:
        return "Stub OCR text result"

    def ground_coordinates(self, element_id: str, image_data: bytes) -> Dict[str, int]:
        return {"x": 50, "y": 50, "width": 100, "height": 30}
