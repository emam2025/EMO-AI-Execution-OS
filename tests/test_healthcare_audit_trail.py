import pytest
from core.industrial.healthcare_twin import HealthcareTwin, HealthcareTwinAssetType
from core.industrial.healthcare_data_pipeline import HealthcareDataPipeline
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
        self.approval_requests.append({"agent_id": agent_id, "action": action, "payload": payload})
        return True


def test_healthcare_safety_gate_audit_trail_completeness():
    event_bus = MockEventBus()
    twin = HealthcareTwin(event_bus)
    approval_gate = MockApprovalGate()
    
    agent = ComplianceAuditorAgent(
        identity=AgentIdentity(id="agent-1", tenant_id="t", org_id=None, name="Test", agent_type="compliance"),
        healthcare_twin=twin,
        event_bus=event_bus,
        approval_gate=approval_gate,
    )
    
    result_allowed = agent.audit_data_access(
        asset_id="pat-001",
        action_type="observe",
        trust_level="UNTRUSTED",
        requested_by="system",
    )
    assert result_allowed["allowed"] is True
    
    result_blocked = agent.audit_data_access(
        asset_id="pat-001",
        action_type="patient_data_export",
        trust_level="UNTRUSTED",
        requested_by="external",
    )
    assert result_blocked["allowed"] is False
    assert result_blocked["violation_type"] == "UNAUTHORIZED_CONTROL_WRITE"
    
    violation_count = len([e for e in event_bus.published_events if e.topic == EventTopic.COMPLIANCE_VIOLATION])
    assert violation_count == 1
    assert event_bus.published_events[-1].payload["action_type"] == "patient_data_export"


def test_healthcare_data_pipeline_audit_trail_records_ingestion():
    event_bus = MockEventBus()
    twin = HealthcareTwin(event_bus)
    pipeline = HealthcareDataPipeline(event_bus, twin)
    
    result = pipeline.ingest_healthcare_data(
        connector_id="fhir-001",
        data={
            "action_type": "observe",
            "asset_id": "pat-001",
            "asset_type": "patient_record",
            "state_update": {"heart_rate": 78},
        },
        trust_level="UNTRUSTED",
    )
    assert result["status"] == "success"
    assert result["asset_id"] == "pat-001"
    
    twin_state = twin.get_twin_state("pat-001")
    assert twin_state is not None
    assert twin_state.version == 1
    assert len(twin_state.audit_trail) == 1
    assert "state_snapshot" in twin_state.audit_trail[0]
    assert "version" in twin_state.audit_trail[0]
    assert twin_state.audit_trail[0]["version"] == 1
    
    pipeline.ingest_healthcare_data(
        connector_id="mqtt-001",
        data={
            "action_type": "control_write",
            "asset_id": "dev-001",
            "asset_type": "medical_device",
            "state_update": {"mode": "manual"},
        },
        trust_level="UNTRUSTED",
    )
    
    safety_violations = [e for e in event_bus.published_events if e.topic == EventTopic.SAFETY_VIOLATION]
    assert len(safety_violations) == 1
    assert safety_violations[0].payload["action_type"] == "control_write"


def test_healthcare_twin_audit_trail_records_operational_events():
    event_bus = MockEventBus()
    twin = HealthcareTwin(event_bus)
    
    twin.update_twin_state(
        asset_id="pat-001",
        asset_type=HealthcareTwinAssetType.PATIENT_RECORD,
        new_state={"vitals": {"heart_rate": 75, "spo2": 98}, "status": "admitted"},
        action="admission",
    )
    
    twin.update_twin_state(
        asset_id="pat-001",
        asset_type=HealthcareTwinAssetType.PATIENT_RECORD,
        new_state={"vitals": {"heart_rate": 120, "spo2": 92}, "status": "critical"},
        action="vitals_update",
    )
    
    audit_trail = twin.get_audit_trail("pat-001")
    assert len(audit_trail) == 2
    assert audit_trail[0]["action"] == "admission"
    assert audit_trail[0]["version"] == 1
    assert audit_trail[1]["action"] == "vitals_update"
    assert audit_trail[1]["version"] == 2
    assert audit_trail[1]["state_snapshot"]["status"] == "critical"
    
    twin_state = twin.get_twin_state("pat-001")
    assert twin_state.version == 2
    
    twin_updated_events = [e for e in event_bus.published_events if e.topic == EventTopic.TWIN_STATE_UPDATED]
    assert len(twin_updated_events) == 2


def test_healthcare_trust_level_enforcement_audit():
    event_bus = MockEventBus()
    twin = HealthcareTwin(event_bus)
    
    agent = ComplianceAuditorAgent(
        identity=AgentIdentity(id="agent-1", tenant_id="t", org_id=None, name="Test", agent_type="compliance"),
        healthcare_twin=twin,
        event_bus=event_bus,
        approval_gate=MockApprovalGate(),
    )
    
    result_untrusted = agent.audit_data_access(
        asset_id="dev-001",
        action_type="device_reconfiguration",
        trust_level="UNTRUSTED",
        requested_by="external",
    )
    assert result_untrusted["allowed"] is False
    assert result_untrusted["violation_type"] == "UNAUTHORIZED_CONTROL_WRITE"
    
    result_trusted = agent.audit_data_access(
        asset_id="dev-001",
        action_type="device_reconfiguration",
        trust_level="TRUSTED",
        requested_by="clinician",
    )
    assert result_trusted["allowed"] is True
    assert result_trusted["requires_approval"] is True
    
    violation_events = [e for e in event_bus.published_events if e.topic == EventTopic.COMPLIANCE_VIOLATION]
    assert len(violation_events) == 1
    assert violation_events[0].payload["trust_level"] == "UNTRUSTED"
    assert violation_events[0].payload["violation_type"] == "UNAUTHORIZED_CONTROL_WRITE"


def test_healthcare_e2e_full_audit_trail_verification():
    event_bus = MockEventBus()
    twin = HealthcareTwin(event_bus)
    pipeline = HealthcareDataPipeline(event_bus, twin)
    approval_gate = MockApprovalGate()
    
    compliance = ComplianceAuditorAgent(
        identity=AgentIdentity(id="agent-c", tenant_id="t", org_id=None, name="Comp", agent_type="compliance"),
        healthcare_twin=twin,
        event_bus=event_bus,
        approval_gate=approval_gate,
    )
    
    monitor = PatientMonitorAgent(
        identity=AgentIdentity(id="agent-m", tenant_id="t", org_id=None, name="Mon", agent_type="monitor"),
        healthcare_twin=twin,
        event_bus=event_bus,
    )
    
    pipeline.ingest_healthcare_data(
        connector_id="fhir-001",
        data={"action_type": "observe", "asset_id": "pat-001", "asset_type": "patient_record",
              "state_update": {"vitals": {"heart_rate": 75, "spo2": 98}, "status": "admitted"}},
        trust_level="UNTRUSTED",
    )
    
    monitor.monitor_patient("pat-001")
    
    twin_state = twin.get_twin_state("pat-001")
    assert twin_state is not None
    assert twin_state.version >= 1
    
    audit_length_before = len(twin_state.audit_trail)
    
    result = compliance.audit_data_access(
        asset_id="pat-001",
        action_type="patient_data_export",
        trust_level="UNTRUSTED",
        requested_by="external_system",
    )
    assert result["allowed"] is False
    
    pipeline.ingest_healthcare_data(
        connector_id="mqtt-001",
        data={"action_type": "control_write", "asset_id": "dev-001", "asset_type": "medical_device",
              "state_update": {"mode": "manual", "tidal_volume": 500}},
        trust_level="UNTRUSTED",
    )
    
    all_twins = twin.list_all_twins()
    assert "pat-001" in all_twins
    assert all_twins["pat-001"].asset_type == HealthcareTwinAssetType.PATIENT_RECORD
    
    twin_state_final = twin.get_twin_state("pat-001")
    assert twin_state_final is not None
    assert twin_state_final.version >= 1
    assert len(twin_state_final.audit_trail) >= audit_length_before
    assert "vitals" in twin_state_final.state
    
    event_topics = [e.topic for e in event_bus.published_events]
    assert EventTopic.TWIN_STATE_UPDATED in event_topics
    assert EventTopic.PATIENT_VITALS_UPDATED in event_topics
    assert EventTopic.COMPLIANCE_VIOLATION in event_topics
    assert EventTopic.SAFETY_VIOLATION in event_topics