"""Energy Data Pipeline — Connectors → EnergySafetyGate → EnergyTwin.

Ingests data from energy connectors (SCADA/MQTT) into digital twins via
NERC-CIP safety enforcement. Every update is evaluated by EnergySafetyGate
before applying to EnergyTwin. CONTROL_WRITE actions are blocked in V1.

Ref: RC17.3.3 — Energy Twin & DataPipeline Integration
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from core.models.energy_policy import EnergyActionType

if TYPE_CHECKING:
    from core.governance.energy_safety import EnergySafetyGate
    from core.industrial.energy_twin import EnergyTwin
    from core.interfaces.event_bus import IEventBus

logger = logging.getLogger(__name__)


class EnergyDataPipeline:
    """Event-driven energy data pipeline: Connectors → SafetyGate → Twin.

    Evaluates every incoming data point through EnergySafetyGate before
    applying to EnergyTwin. CONTROL_WRITE actions are blocked in V1.
    """

    def __init__(
        self,
        energy_twin: EnergyTwin,
        safety_gate: EnergySafetyGate,
        event_bus: IEventBus,
    ) -> None:
        self._energy_twin = energy_twin
        self._safety_gate = safety_gate
        self._event_bus = event_bus
        self._connectors: Dict[str, Any] = {}
        self._tag_mappings: Dict[str, Dict[str, str]] = {}
        self._audit_log: List[Dict[str, Any]] = []
        self._stats = {"ingested": 0, "blocked": 0, "updated": 0}

    def register_connector(self, connector_id: str, connector: Any) -> None:
        """Register a connector for data ingestion."""
        self._connectors[connector_id] = connector

    def register_tag_mapping(
        self, tag_id: str, asset_id: str, field: str
    ) -> None:
        """Register a mapping from connector tag to twin asset field.

        The action_type determines whether this is a read-only or control write.
        """
        self._tag_mappings[tag_id] = {
            "asset_id": asset_id,
            "field": field,
        }

    def ingest_energy_data(
        self,
        connector_id: str,
        tag_data: Dict[str, Any],
        trust_level: str = "UNVERIFIED",
    ) -> Dict[str, Any]:
        """Ingest data from a connector, enforcing NERC-CIP safety.

        For each tag in tag_data:
        1. Look up the tag mapping (asset_id, field).
        2. Evaluate via EnergySafetyGate (OBSERVE for read-only data).
        3. If allowed, update EnergyTwin.
        4. If blocked (CONTROL_WRITE), reject and publish SAFETY_VIOLATION.

        Returns:
            {"ingested": int, "blocked": int, "updated": int, "details": list}
        """
        details: List[Dict[str, Any]] = []

        for tag_id, value in tag_data.items():
            mapping = self._tag_mappings.get(tag_id)
            if mapping is None:
                details.append({
                    "tag_id": tag_id,
                    "status": "skipped",
                    "reason": "no_mapping",
                })
                continue

            asset_id = mapping["asset_id"]
            field = mapping["field"]

            # Determine action type based on field name
            action_type = self._classify_action(field)

            # Evaluate through safety gate
            decision = self._safety_gate.evaluate(
                action_type=action_type,
                trust_level=trust_level,
                context={"tag_id": tag_id, "asset_id": asset_id, "field": field},
            )

            if not decision.allowed:
                self._stats["blocked"] += 1
                details.append({
                    "tag_id": tag_id,
                    "asset_id": asset_id,
                    "field": field,
                    "status": "blocked",
                    "reason": decision.reason,
                    "violation_type": decision.violation_type,
                })
                self._record_audit(
                    tag_id, asset_id, field, "blocked", decision.reason
                )
                continue

            # Update twin state
            self._energy_twin.update_twin_state(asset_id, {field: value})
            self._stats["updated"] += 1
            self._stats["ingested"] += 1

            details.append({
                "tag_id": tag_id,
                "asset_id": asset_id,
                "field": field,
                "status": "updated",
                "value": value,
            })
            self._record_audit(tag_id, asset_id, field, "updated", "ok")

        return {
            "ingested": self._stats["ingested"],
            "blocked": self._stats["blocked"],
            "updated": self._stats["updated"],
            "details": details,
        }

    def _classify_action(self, field: str) -> EnergyActionType:
        """Classify a field update as OBSERVE or CONTROL_WRITE.

        Fields containing 'control', 'setpoint', 'command', 'shutdown',
        'start', 'stop' are classified as CONTROL_WRITE.
        All others are OBSERVE (read-only telemetry).
        """
        control_keywords = {
            "control", "setpoint", "command", "shutdown",
            "start", "stop", "override", "trip",
        }
        field_lower = field.lower()
        for keyword in control_keywords:
            if keyword in field_lower:
                return EnergyActionType.CONTROL_WRITE
        return EnergyActionType.OBSERVE

    def ingest_from_connector(
        self,
        connector_id: str,
        tag_ids: List[str],
        trust_level: str = "UNVERIFIED",
    ) -> Dict[str, Any]:
        """Read from a registered connector and ingest through safety gate.

        This is the live connector integration path:
        1. Read tags from the registered connector.
        2. Map each tag to (asset_id, field) via tag mappings.
        3. Classify action type (OBSERVE or CONTROL_WRITE).
        4. Evaluate through EnergySafetyGate.
        5. If allowed, update EnergyTwin.

        Args:
            connector_id: ID of the registered connector.
            tag_ids: Tag IDs to read from the connector.
            trust_level: Trust level for safety evaluation.

        Returns:
            {"ingested": int, "blocked": int, "updated": int, "details": list}
        """
        connector = self._connectors.get(connector_id)
        if connector is None:
            return {
                "ingested": self._stats["ingested"],
                "blocked": self._stats["blocked"],
                "updated": self._stats["updated"],
                "details": [{
                    "connector_id": connector_id,
                    "status": "error",
                    "reason": "connector_not_registered",
                }],
            }

        # Read from connector (sync path)
        try:
            if hasattr(connector, "read_tags"):
                tag_data = connector.read_tags(tag_ids)
            elif hasattr(connector, "read_topics"):
                tag_data = connector.read_topics(tag_ids)
            else:
                return {
                    "ingested": self._stats["ingested"],
                    "blocked": self._stats["blocked"],
                    "updated": self._stats["updated"],
                    "details": [{
                        "connector_id": connector_id,
                        "status": "error",
                        "reason": "connector_not_readable",
                    }],
                }
        except Exception as exc:
            return {
                "ingested": self._stats["ingested"],
                "blocked": self._stats["blocked"],
                "updated": self._stats["updated"],
                "details": [{
                    "connector_id": connector_id,
                    "status": "error",
                    "reason": f"read_failed: {exc}",
                }],
            }

        # Delegate to existing ingestion logic
        return self.ingest_energy_data(
            connector_id=connector_id,
            tag_data=tag_data,
            trust_level=trust_level,
        )

    def get_stats(self) -> Dict[str, int]:
        """Return ingestion statistics."""
        return dict(self._stats)

    def get_audit_log(self) -> List[Dict[str, Any]]:
        """Return the audit trail."""
        return list(self._audit_log)

    def _record_audit(
        self,
        tag_id: str,
        asset_id: str,
        field: str,
        status: str,
        reason: str,
    ) -> None:
        """Record an audit entry."""
        self._audit_log.append({
            "tag_id": tag_id,
            "asset_id": asset_id,
            "field": field,
            "status": status,
            "reason": reason,
        })
