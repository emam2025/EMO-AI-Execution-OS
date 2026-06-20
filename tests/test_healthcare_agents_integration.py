import pytest
from unittest.mock import Mock
from core.agents.healthcare.patient_monitor_agent import PatientMonitorAgent
from core.agents.healthcare.device_manager_agent import DeviceManagerAgent
from core.agents.healthcare.compliance_auditor_agent import ComplianceAuditorAgent
from core.agents.healthcare.healthcare_analyst_agent import HealthcareAnalystAgent
from core.industrial.healthcare_twin import HealthcareTwin, HealthcareTwinAssetType
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


def test_patient_monitor_reads_twin_and_publishes_event():
    event_bus = MockEventBus()
    twin = HealthcareTwin(event_bus)
    
    twin.update_twin_state(
        asset_id="pat-001",
        asset_type=HealthcareTwinAssetType.PATIENT_RECORD,
        new_state={"vitals": {"heart_rate": 85, "spo2": 98}},
        action="initial",
    )
    
    agent = PatientMonitorAgent(
        identity=AgentIdentity(
            id="agent-patient-monitor",
            tenant_id="test-tenant",
            org_id=None,
            name="PatientMonitor",
            agent_type="patient_monitor",
        ),
        healthcare_twin=twin,
        event_bus=event_bus,
    )
    
    result = agent.monitor_patient("pat-001")
    
    assert result["patient_id"] == "pat-001"
    assert result["vitals"]["heart_rate"] == 85
    assert result["anomaly_detected"] is False
    
    vitals_events = [e for e in event_bus.published_events if e.topic == EventTopic.PATIENT_VITALS_UPDATED]
    assert len(vitals_events) == 1
    assert vitals_events[0].payload["patient_id"] == "pat-001"


def test_device_manager_recommends_maintenance_via_twin():
    event_bus = MockEventBus()
    twin = HealthcareTwin(event_bus)
    
    twin.update_twin_state(
        asset_id="dev-001",
        asset_type=HealthcareTwinAssetType.MEDICAL_DEVICE,
        new_state={
            "status": "running",
            "measurements": {"tidal_volume": 350, "peak_pressure": 35},
            "battery_level": 15,
        },
        action="initial",
    )
    
    agent = DeviceManagerAgent(
        identity=AgentIdentity(
            id="agent-device-manager",
            tenant_id="test-tenant",
            org_id=None,
            name="DeviceManager",
            agent_type="device_manager",
        ),
        healthcare_twin=twin,
        event_bus=event_bus,
    )
    
    result = agent.check_device("dev-001")
    
    assert result["device_id"] == "dev-001"
    assert "RECOMMEND_CALIBRATION" in result["recommendations"]
    assert "RECOMMEND_MAINTENANCE" in result["recommendations"]
    assert "RECOMMEND_BATTERY_REPLACEMENT" in result["recommendations"]
    
    alert_events = [e for e in event_bus.published_events if e.topic == EventTopic.PREDICTIVE_ALERT]
    assert len(alert_events) == 1
    assert alert_events[0].payload["device_id"] == "dev-001"


def test_compliance_auditor_blocks_untrusted_data_export():
    event_bus = MockEventBus()
    twin = HealthcareTwin(event_bus)
    
    agent = ComplianceAuditorAgent(
        identity=AgentIdentity(
            id="agent-compliance",
            tenant_id="test-tenant",
            org_id=None,
            name="ComplianceAuditor",
            agent_type="compliance_auditor",
        ),
        healthcare_twin=twin,
        event_bus=event_bus,
    )
    
    result = agent.audit_data_access(
        asset_id="pat-001",
        action_type="patient_data_export",
        trust_level="UNTRUSTED",
        requested_by="external_system",
    )
    
    assert result["allowed"] is False
    assert result["violation_type"] == "UNAUTHORIZED_CONTROL_WRITE"
    assert result["requires_approval"] is True
    
    violation_events = [e for e in event_bus.published_events if e.topic == EventTopic.COMPLIANCE_VIOLATION]
    assert len(violation_events) == 1
    assert violation_events[0].payload["action_type"] == "patient_data_export"
    assert violation_events[0].payload["trust_level"] == "UNTRUSTED"


def test_healthcare_analyst_predicts_twin_state():
    event_bus = MockEventBus()
    twin = HealthcareTwin(event_bus)
    
    twin.update_twin_state(
        asset_id="pat-001",
        asset_type=HealthcareTwinAssetType.PATIENT_RECORD,
        new_state={"heart_rate": 78, "trend": "stable"},
        action="initial",
    )
    
    agent = HealthcareAnalystAgent(
        identity=AgentIdentity(
            id="agent-analyst",
            tenant_id="test-tenant",
            org_id=None,
            name="HealthcareAnalyst",
            agent_type="healthcare_analyst",
        ),
        healthcare_twin=twin,
        event_bus=event_bus,
    )
    
    result = agent.analyze_trends("pat-001", horizon_minutes=120)
    
    assert result["asset_id"] == "pat-001"
    assert result["asset_type"] == "patient_record"
    assert "prediction" in result
    assert "confidence" in result
    
    trend_events = [e for e in event_bus.published_events if e.topic == EventTopic.TREND_ANALYSIS_REPORT]
    assert len(trend_events) == 1
    assert trend_events[0].payload["asset_id"] == "pat-001"


def test_agent_critical_action_requires_approval_gate():
    event_bus = MockEventBus()
    twin = HealthcareTwin(event_bus)
    approval_gate = MockApprovalGate()
    
    agent = ComplianceAuditorAgent(
        identity=AgentIdentity(
            id="agent-compliance",
            tenant_id="test-tenant",
            org_id=None,
            name="ComplianceAuditor",
            agent_type="compliance_auditor",
        ),
        healthcare_twin=twin,
        event_bus=event_bus,
        approval_gate=approval_gate,
    )
    
    assert agent._approval_gate is approval_gate
    
    result = agent.audit_data_access(
        asset_id="pat-001",
        action_type="control_write",
        trust_level="TRUSTED",
        requested_by="clinician",
    )
    
    assert result["allowed"] is True
    assert result["requires_approval"] is True


def test_multiple_agents_isolation_in_healthcare_twin():
    event_bus = MockEventBus()
    twin = HealthcareTwin(event_bus)
    
    twin.update_twin_state(
        asset_id="pat-001",
        asset_type=HealthcareTwinAssetType.PATIENT_RECORD,
        new_state={"vitals": {"heart_rate": 78}},
        action="initial",
    )
    
    twin.update_twin_state(
        asset_id="dev-001",
        asset_type=HealthcareTwinAssetType.MEDICAL_DEVICE,
        new_state={"status": "online", "measurements": {"tidal_volume": 500}},
        action="initial",
    )
    
    patient_agent = PatientMonitorAgent(
        identity=AgentIdentity(
            id="agent-patient-1",
            tenant_id="test-tenant",
            org_id=None,
            name="PatientMonitor1",
            agent_type="patient_monitor",
        ),
        healthcare_twin=twin,
        event_bus=event_bus,
    )
    
    device_agent = DeviceManagerAgent(
        identity=AgentIdentity(
            id="agent-device-1",
            tenant_id="test-tenant",
            org_id=None,
            name="DeviceManager1",
            agent_type="device_manager",
        ),
        healthcare_twin=twin,
        event_bus=event_bus,
    )
    
    patient_result = patient_agent.monitor_patient("pat-001")
    device_result = device_agent.check_device("dev-001")
    
    assert patient_result["patient_id"] == "pat-001"
    assert device_result["device_id"] == "dev-001"
    
    patient_twin = twin.get_twin_state("pat-001")
    device_twin = twin.get_twin_state("dev-001")
    
    assert patient_twin.asset_type == HealthcareTwinAssetType.PATIENT_RECORD
    assert device_twin.asset_type == HealthcareTwinAssetType.MEDICAL_DEVICE
    assert patient_twin.state["vitals"]["heart_rate"] == 78
    assert device_twin.state["measurements"]["tidal_volume"] == 500