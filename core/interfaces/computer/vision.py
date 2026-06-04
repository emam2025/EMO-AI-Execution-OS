from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class IVisionWorker(Protocol):
    """Protocol for computer vision workers.

    LAW 1: Conforms to IVisionWorker interface.
    LAW 10: External engines may fail — all calls MUST be guarded.
    RULE 1: Deterministic — same image + config → same result.
    """

    def analyze_image(self, image_data: bytes, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Analyze image content and return structured description.

        Args:
            image_data: Raw image bytes (PNG/JPEG).
            config: Optional analysis configuration (model, threshold, etc.).

        Returns:
            Dict with analysis results (labels, confidence, regions).
        """
        ...

    def detect_ui_elements(self, image_data: bytes) -> List[Dict[str, Any]]:
        """Detect UI elements in a screenshot.

        Args:
            image_data: Raw image bytes.

        Returns:
            List of detected elements, each with type, bounding_box, confidence.
        """
        ...

    def ocr_text(self, image_data: bytes, languages: Optional[List[str]] = None) -> str:
        """Extract text from image using OCR.

        Args:
            image_data: Raw image bytes.
            languages: Optional list of language codes.

        Returns:
            Extracted text string.
        """
        ...

    def ground_coordinates(self, element_id: str, image_data: bytes) -> Dict[str, int]:
        """Ground a UI element identifier to screen coordinates.

        Args:
            element_id: Identifier from detect_ui_elements output.
            image_data: Raw image bytes for spatial grounding.

        Returns:
            Dict with x, y, width, height of the element.
        """
        ...
