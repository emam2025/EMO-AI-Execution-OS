import pytest
from core.industrial.healthcare_twin import HealthcareTwin, HealthcareTwinAssetType
from core.agents.healthcare.patient_monitor_agent import PatientMonitorAgent
from core.agents.healthcare.compliance_auditor_agent import ComplianceAuditorAgent
from core.models.agent import AgentIdentity
from core.models.event import EventTopic


class MockEventBus:
    def __init__(self):
        self.published_events = []
    
    def publish(self, topic: EventTopic, event):
        self.published_events.append(event)
    
    def subscribe(self, topic: EventTopic, handler):
        pass


class MockApprovalGate:
    def __init__(self):
        self.approval_requests = []
    
    def request_approval(self, agent_id: str, action: str, payload: dict) -> bool:
        self.approval_requests.append({
            "agent_id": agent_id,
            "action": action,
            "payload": payload,
        })
        return True


def test_healthcare_e2e_critical_scenario():
    # ── Phase 1: Setup Infrastructure ────────────────────────────────────────
    event_bus = MockEventBus()
    approval_gate = MockApprovalGate()
    twin = HealthcareTwin(event_bus)

    patient_agent = PatientMonitorAgent(
        identity=AgentIdentity(
            id="agent-patient-monitor-e2e",
            tenant_id="hospital-001",
            org_id=None,
            name="PatientMonitorE2E",
            agent_type="patient_monitor",
        ),
        healthcare_twin=twin,
        event_bus=event_bus,
    )

    compliance_agent = ComplianceAuditorAgent(
        identity=AgentIdentity(
            id="agent-compliance-e2e",
            tenant_id="hospital-001",
            org_id=None,
            name="ComplianceAuditorE2E",
            agent_type="compliance_auditor",
        ),
        healthcare_twin=twin,
        event_bus=event_bus,
        approval_gate=approval_gate,
    )

    assert twin is not None
    assert patient_agent is not None
    assert compliance_agent is not None
    assert len(event_bus.published_events) == 0

    # ── Phase 2: Normal Patient Monitoring ────────────────────────────────────
    twin.update_twin_state(
        asset_id="pat-001",
        asset_type=HealthcareTwinAssetType.PATIENT_RECORD,
        new_state={
            "vitals": {"heart_rate": 75, "spo2": 98},
            "status": "admitted",
        },
        action="admission",
    )

    normal_result = patient_agent.monitor_patient("pat-001")

    assert normal_result["patient_id"] == "pat-001"
    assert normal_result["vitals"]["heart_rate"] == 75
    assert normal_result["vitals"]["spo2"] == 98
    assert normal_result["anomaly_detected"] is False

    vitals_events = [
        e for e in event_bus.published_events
        if e.topic == EventTopic.PATIENT_VITALS_UPDATED
    ]
    assert len(vitals_events) >= 1
    last_vitals_event = vitals_events[-1]
    assert last_vitals_event.payload["patient_id"] == "pat-001"
    assert last_vitals_event.payload["status"] == "normal"

    # ── Phase 3: Anomaly Detection ───────────────────────────────────────────
    twin.update_twin_state(
        asset_id="pat-001",
        asset_type=HealthcareTwinAssetType.PATIENT_RECORD,
        new_state={
            "vitals": {"heart_rate": 120, "spo2": 92},
            "status": "critical",
        },
        action="vitals_update",
    )

    critical_result = patient_agent.monitor_patient("pat-001")

    assert critical_result["patient_id"] == "pat-001"
    assert critical_result["vitals"]["heart_rate"] == 120
    assert critical_result["vitals"]["spo2"] == 92
    assert critical_result["anomaly_detected"] is True
    assert len(critical_result["anomaly_details"]) > 0

    anomaly_events = [
        e for e in event_bus.published_events
        if e.topic == EventTopic.ANOMALY_DETECTED
    ]
    assert len(anomaly_events) >= 1
    last_anomaly = anomaly_events[-1]
    assert last_anomaly.payload["patient_id"] == "pat-001"
    assert "Abnormal heart rate" in str(last_anomaly.payload["anomalies"]) or \
           "Low SpO2" in str(last_anomaly.payload["anomalies"])

    # ── Phase 4: Compliance Audit for Intervention ───────────────────────────
    untrusted_export_result = compliance_agent.audit_data_access(
        asset_id="pat-001",
        action_type="patient_data_export",
        trust_level="UNTRUSTED",
        requested_by="external_research_system",
    )

    assert untrusted_export_result["allowed"] is False
    assert untrusted_export_result["violation_type"] == "UNAUTHORIZED_CONTROL_WRITE"
    assert untrusted_export_result["requires_approval"] is True

    violation_events = [
        e for e in event_bus.published_events
        if e.topic == EventTopic.COMPLIANCE_VIOLATION
    ]
    assert len(violation_events) >= 1
    last_violation = violation_events[-1]
    assert last_violation.payload["action_type"] == "patient_data_export"
    assert last_violation.payload["trust_level"] == "UNTRUSTED"
    assert last_violation.payload["requested_by"] == "external_research_system"

    # ── Phase 5: Trusted Intervention & Approval ─────────────────────────────
    trusted_control_result = compliance_agent.audit_data_access(
        asset_id="dev-001",
        action_type="control_write",
        trust_level="TRUSTED",
        requested_by="attending_physician",
    )

    assert trusted_control_result["allowed"] is True
    assert trusted_control_result["requires_approval"] is True

    approval_granted = approval_gate.request_approval(
        agent_id="attending_physician",
        action="control_write",
        payload={"asset_id": "dev-001", "action": "adjust_ventilator"},
    )

    assert approval_granted is True
    assert len(approval_gate.approval_requests) == 1
    assert approval_gate.approval_requests[0]["action"] == "control_write"

    # ── Phase 6: EventStore Audit Trail Verification ─────────────────────────
    all_events = event_bus.published_events

    event_topics = [e.topic for e in all_events]
    assert EventTopic.TWIN_STATE_UPDATED in event_topics
    assert EventTopic.PATIENT_VITALS_UPDATED in event_topics
    assert EventTopic.ANOMALY_DETECTED in event_topics
    assert EventTopic.COMPLIANCE_VIOLATION in event_topics

    for event in all_events:
        assert hasattr(event, "topic")
        assert hasattr(event, "payload")
        assert isinstance(event.payload, dict)

    twin_state = twin.get_twin_state("pat-001")
    assert twin_state is not None
    assert len(twin_state.audit_trail) >= 2
    assert twin_state.version >= 2

    audit_actions = [entry["action"] for entry in twin_state.audit_trail]
    assert "admission" in audit_actions or "ingest:OBSERVE" in audit_actions or \
           any("admission" in str(a) for a in audit_actions)

    all_twins = twin.list_all_twins()
    assert "pat-001" in all_twins
    assert all_twins["pat-001"].asset_type == HealthcareTwinAssetType.PATIENT_RECORD