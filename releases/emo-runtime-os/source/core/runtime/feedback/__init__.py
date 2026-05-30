"""D9 — Runtime Intelligence Feedback Loop.

Exports all feedback loop components:
  - FeedbackLoop:          Core orchestrator (capture → analyze → adjust → alert)
  - DynamicCouplingAdjuster: Score computation + threshold + file commit
  - HotspotDetector:       Execution frequency + failure patterns + decomposition
  - ArchitectureAlert:     Violation evaluation + severity + enforcement gate
  - RateLimiter:           Adjustment/alert rate tracking per scope
  - FeedbackStateMachine:  8-state feedback lifecycle machine

Ref: DEVELOPER.md §5.3 (Self-Tuning), §5.4 (Guardrails)
Ref: Canon LAW 5, LAW 7, LAW 11, LAW 14-16
"""

from core.runtime.feedback.feedback_loop import FeedbackLoop
from core.runtime.feedback.coupling_adjuster import DynamicCouplingAdjuster
from core.runtime.feedback.hotspot_detector import HotspotDetector
from core.runtime.feedback.architecture_alert import ArchitectureAlert
from core.runtime.feedback.rate_limiter import RateLimiter
from core.runtime.feedback.state_machine import FeedbackStateMachine

__all__ = [
    "FeedbackLoop",
    "DynamicCouplingAdjuster",
    "HotspotDetector",
    "ArchitectureAlert",
    "RateLimiter",
    "FeedbackStateMachine",
]
