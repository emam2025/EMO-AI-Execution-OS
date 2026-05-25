"""Phase F4 — AlertRouter implementation.  # LAW-5 # RULE-3

Implements IAlertRouter: evaluate_threshold, route_alert,
suppress_duplicate, acknowledge.

LAW 5: Alerts routed to configured targets; CRITICAL always to
       runtime.alert.critical.
RULE 3: Duplicate suppression prevents alert storms.

Ref: Canon LAW 5 (Observability), RULE 3 (Recoverability)
Ref: artifacts/design/f4/protocols/01_observability_protocols.py::IAlertRouter
"""

from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional

from core.runtime.models.observability_models import (
    AggregatedMetric,
    AlertPayload,
    AlertReceipt,
    AlertRule,
    Severity,
)

logger = logging.getLogger("emo_ai.observability.alert_router")


class AlertRouter:  # ←→ IAlertRouter  # LAW-5
    """Concrete implementation of IAlertRouter.

    Evaluates metrics against rules, routes alerts with suppression,
    and supports acknowledgement of active alerts.
    """

    def __init__(self) -> None:
        self._rules: Dict[str, AlertRule] = {}
        self._active_alerts: Dict[str, AlertReceipt] = {}
        self._acknowledged_alerts: set = set()
        self._suppression_cooldowns: Dict[str, float] = {}
        self._routing_log: List[AlertReceipt] = []

    @property
    def active_alerts(self) -> Dict[str, AlertReceipt]:
        return dict(self._active_alerts)

    @property
    def routing_log(self) -> List[AlertReceipt]:
        return list(self._routing_log)

    def register_rule(self, rule: AlertRule) -> None:
        self._rules[rule.alert_id] = rule

    # ── evaluate_threshold ──────────────────────────────────────

    def evaluate_threshold(  # LAW-5
        self,
        metric: AggregatedMetric,
        rule: AlertRule,
    ) -> bool:
        value = float(metric.count)
        threshold = rule.threshold

        ops = {
            "gt": lambda v, t: v > t,
            "lt": lambda v, t: v < t,
            "gte": lambda v, t: v >= t,
            "lte": lambda v, t: v <= t,
            "eq": lambda v, t: v == t,
        }

        op_fn = ops.get(rule.operator)
        if op_fn is None:
            logger.warning("Unknown operator: %s", rule.operator)
            return False

        return op_fn(value, threshold)

    # ── route_alert ─────────────────────────────────────────────

    def route_alert(  # LAW-5, RULE-5
        self,
        alert_id: str,
        severity: Severity,
        payload: Dict[str, str],
    ) -> AlertReceipt:
        if alert_id in self._active_alerts:
            existing = self._active_alerts[alert_id]
            logger.debug("Alert %s already active (idempotent)", alert_id)
            return existing

        rule = self._rules.get(alert_id)
        suppression_key = payload.get("suppression_key", rule.suppression_key if rule else "")

        suppressed = False
        if suppression_key:
            suppressed = self.suppress_duplicate(suppression_key)

        routing_target = "runtime.alert.critical" if severity == Severity.CRITICAL else (
            payload.get("routing_target", rule.suppression_key if rule else "runtime.alert.default") if not suppressed else "suppressed"
        )

        now_ns = time.time_ns()
        receipt = AlertReceipt(
            alert_id=alert_id,
            severity=severity,
            timestamp_ns=now_ns,
            suppressed=suppressed,
            routed_to=routing_target,
        )

        if not suppressed:
            self._active_alerts[alert_id] = receipt

        self._routing_log.append(receipt)
        logger.info(
            "Routed alert %s severity=%s target=%s suppressed=%s",
            alert_id, severity.value, routing_target, suppressed,
        )
        return receipt

    # ── suppress_duplicate ──────────────────────────────────────

    def suppress_duplicate(  # RULE-3
        self,
        suppression_key: str,
        cooldown_sec: float = 60.0,
    ) -> bool:
        now = time.time()
        cooldown_until = self._suppression_cooldowns.get(suppression_key, 0.0)

        if now < cooldown_until:
            logger.debug("Suppressed alert key=%s (cooldown active)", suppression_key)
            return True

        self._suppression_cooldowns[suppression_key] = now + cooldown_sec
        return False

    # ── acknowledge ─────────────────────────────────────────────

    def acknowledge(  # LAW-5
        self,
        alert_id: str,
        acknowledgement: str,
    ) -> AlertReceipt:
        receipt = self._active_alerts.pop(alert_id, None)
        if receipt is None:
            logger.warning("Cannot acknowledge unknown alert: %s", alert_id)
            return AlertReceipt(
                alert_id=alert_id,
                severity=Severity.INFO,
                timestamp_ns=time.time_ns(),
                acknowledgement="not_found",
            )

        receipt.acknowledgement = acknowledgement
        self._acknowledged_alerts.add(alert_id)
        logger.info("Acknowledged alert %s: %s", alert_id, acknowledgement)
        return receipt

    def reset(self) -> None:
        self._rules.clear()
        self._active_alerts.clear()
        self._acknowledged_alerts.clear()
        self._suppression_cooldowns.clear()
        self._routing_log.clear()
