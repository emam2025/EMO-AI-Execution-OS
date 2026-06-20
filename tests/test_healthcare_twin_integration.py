import pytest
from unittest.mock import Mock
from core.industrial.healthcare_twin import HealthcareTwin, HealthcareTwinAssetType
from core.industrial.healthcare_data_pipeline import HealthcareDataPipeline
from core.models.event import EventTopic


class MockEventBus:
    def __init__(self):
        self.published_events = []
    
    def publish(self, topic: EventTopic, event):
        self.published_events.append(event)
    
    def subscribe(self, topic: EventTopic, handler):
        pass


def test_ingest_read_only_data_updates_twin():
    event_bus = MockEventBus()
    twin = HealthcareTwin(event_bus)
    pipeline = HealthcareDataPipeline(event_bus, twin)
    
    result = pipeline.ingest_healthcare_data(
        connector_id="fhir-001",
        data={
            "action_type": "OBSERVE",
            "asset_id": "pat-001",
            "asset_type": "patient_record",
            "state_update": {"heart_rate": 78, "status": "stable"},
        },
        trust_level="UNTRUSTED",
    )
    
    assert result["status"] == "success"
    assert result["asset_id"] == "pat-001"
    assert result["twin_version"] == 1
    
    twin_state = twin.get_twin_state("pat-001")
    assert twin_state is not None
    assert twin_state.version == 1
    assert twin_state.state["heart_rate"] == 78


def test_ingest_control_write_data_is_blocked_by_safety_gate():
    event_bus = MockEventBus()
    twin = HealthcareTwin(event_bus)
    pipeline = HealthcareDataPipeline(event_bus, twin)
    
    result = pipeline.ingest_healthcare_data(
        connector_id="mqtt-001",
        data={
            "action_type": "control_write",
            "asset_id": "dev-001",
            "asset_type": "medical_device",
            "state_update": {"mode": "manual"},
        },
        trust_level="UNTRUSTED",
    )
    
    assert result["status"] == "blocked"
    assert "TRUSTED" in result["reason"]
    assert result["violation_type"] == "UNAUTHORIZED_CONTROL_WRITE"
    
    twin_state = twin.get_twin_state("dev-001")
    assert twin_state is None


def test_twin_state_version_increments_on_valid_update():
    event_bus = MockEventBus()
    twin = HealthcareTwin(event_bus)
    pipeline = HealthcareDataPipeline(event_bus, twin)
    
    pipeline.ingest_healthcare_data(
        connector_id="fhir-001",
        data={
            "action_type": "OBSERVE",
            "asset_id": "pat-001",
            "asset_type": "patient_record",
            "state_update": {"heart_rate": 78},
        },
        trust_level="UNTRUSTED",
    )
    
    pipeline.ingest_healthcare_data(
        connector_id="fhir-001",
        data={
            "action_type": "ANALYZE",
            "asset_id": "pat-001",
            "asset_type": "patient_record",
            "state_update": {"heart_rate": 80, "trend": "improving"},
        },
        trust_level="UNTRUSTED",
    )
    
    twin_state = twin.get_twin_state("pat-001")
    assert twin_state.version == 2


def test_healthcare_pipeline_publishes_twin_updated_event():
    event_bus = MockEventBus()
    twin = HealthcareTwin(event_bus)
    pipeline = HealthcareDataPipeline(event_bus, twin)
    
    pipeline.ingest_healthcare_data(
        connector_id="fhir-001",
        data={
            "action_type": "OBSERVE",
            "asset_id": "pat-001",
            "asset_type": "patient_record",
            "state_update": {"heart_rate": 78},
        },
        trust_level="UNTRUSTED",
    )
    
    twin_updated_events = [e for e in event_bus.published_events 
                           if e.topic == EventTopic.TWIN_STATE_UPDATED]
    assert len(twin_updated_events) == 1
    assert twin_updated_events[0].payload["asset_id"] == "pat-001"
    assert twin_updated_events[0].payload["new_version"] == 1


def test_healthcare_pipeline_audit_trail_records_ingestion():
    event_bus = MockEventBus()
    twin = HealthcareTwin(event_bus)
    pipeline = HealthcareDataPipeline(event_bus, twin)
    
    pipeline.ingest_healthcare_data(
        connector_id="fhir-001",
        data={
            "action_type": "OBSERVE",
            "asset_id": "pat-001",
            "asset_type": "patient_record",
            "state_update": {"heart_rate": 78},
        },
        trust_level="UNTRUSTED",
    )
    
    audit_trail = twin.get_audit_trail("pat-001")
    assert len(audit_trail) == 1
    assert audit_trail[0]["action"] == "ingest:OBSERVE"
    assert audit_trail[0]["version"] == 1
    assert "heart_rate" in audit_trail[0]["state_snapshot"]


def test_multiple_assets_isolation_in_healthcare_twin():
    event_bus = MockEventBus()
    twin = HealthcareTwin(event_bus)
    pipeline = HealthcareDataPipeline(event_bus, twin)
    
    pipeline.ingest_healthcare_data(
        connector_id="fhir-001",
        data={
            "action_type": "OBSERVE",
            "asset_id": "pat-001",
            "asset_type": "patient_record",
            "state_update": {"heart_rate": 78},
        },
        trust_level="UNTRUSTED",
    )
    
    pipeline.ingest_healthcare_data(
        connector_id="mqtt-001",
        data={
            "action_type": "OBSERVE",
            "asset_id": "dev-001",
            "asset_type": "medical_device",
            "state_update": {"tidal_volume": 500},
        },
        trust_level="UNTRUSTED",
    )
    
    patient_twin = twin.get_twin_state("pat-001")
    device_twin = twin.get_twin_state("dev-001")
    
    assert patient_twin is not None
    assert device_twin is not None
    assert patient_twin.asset_type == HealthcareTwinAssetType.PATIENT_RECORD
    assert device_twin.asset_type == HealthcareTwinAssetType.MEDICAL_DEVICE
    assert patient_twin.state["heart_rate"] == 78
    assert device_twin.state["tidal_volume"] == 500
    
    all_twins = twin.list_all_twins()
    assert len(all_twins) == 2