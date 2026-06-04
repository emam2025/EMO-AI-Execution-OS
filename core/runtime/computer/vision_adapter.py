"""VisionAdapter — Routes IVisionWorker requests to external engines.

LAW 10: External engines may fail — all calls guarded.
RULE 1: Deterministic — same image + config → same structured result.
CORE FREEZE: Zero import of opencv, PIL, or any CV library.

The adapter defines the conversion boundary. Actual CV/ML engines
are injected at the CompositionRoot level as external adapters only.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class VisionAdapter:
    """Adapter for computer vision requests.

    Routes IVisionWorker calls to an external engine (local or cloud).
    Returns structured coordinates/text without importing CV libraries.
    """

    def __init__(self, engine: Any = None) -> None:
        self._engine = engine

    def analyze_image(self, image_data: bytes, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Route analyze_image to external engine.

        Args:
            image_data: Raw image bytes (PNG/JPEG).
            config: Optional analysis configuration.

        Returns:
            Analysis result from engine, or default empty result.
        """
        if self._engine is None:
            return {"labels": [], "confidence": 0.0, "regions": []}
        return self._engine.analyze_image(image_data, config)

    def detect_ui_elements(self, image_data: bytes) -> List[Dict[str, Any]]:
        """Route UI element detection to external engine.

        Args:
            image_data: Raw image bytes.

        Returns:
            List of detected elements from engine, or empty list.
        """
        if self._engine is None:
            return []
        return self._engine.detect_ui_elements(image_data)

    def ocr_text(self, image_data: bytes, languages: Optional[List[str]] = None) -> str:
        """Route OCR request to external engine.

        Args:
            image_data: Raw image bytes.
            languages: Optional language codes.

        Returns:
            Extracted text from engine, or empty string.
        """
        if self._engine is None:
            return ""
        return self._engine.ocr_text(image_data, languages)

    def ground_coordinates(self, element_id: str, image_data: bytes) -> Dict[str, int]:
        """Route coordinate grounding to external engine.

        Args:
            element_id: Element identifier.
            image_data: Raw image bytes.

        Returns:
            Coordinate dict from engine, or default zero rect.
        """
        if self._engine is None:
            return {"x": 0, "y": 0, "width": 0, "height": 0}
        return self._engine.ground_coordinates(element_id, image_data)
