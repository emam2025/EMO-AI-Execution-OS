import pytest
from unittest.mock import Mock, MagicMock
from core.connectors.healthcare.fhir_connector import FHIRConnector
from core.connectors.healthcare.medical_mqtt_connector import MedicalMQTTConnector
from core.connectors.manufacturing.connector_error import ConnectorError
from core.models.event import EventTopic


class MockEventBus:
    def __init__(self):
        self.published_events = []
    
    def publish(self, topic: EventTopic, event):
        self.published_events.append(event)
    
    def subscribe(self, topic: EventTopic, handler):
        pass


def test_fhir_connector_read_patient_record_success():
    event_bus = MockEventBus()
    connector = FHIRConnector(event_bus)
    
    result = connector.read_patient("pat-001")
    
    assert result["resourceType"] == "Patient"
    assert result["id"] == "pat-001"
    assert len(event_bus.published_events) == 1
    assert event_bus.published_events[0].topic == EventTopic.CONNECTOR_READ_SUCCESS
    assert event_bus.published_events[0].payload["resource_path"] == "Patient/pat-001"


def test_fhir_connector_read_missing_resource_raises_error():
    event_bus = MockEventBus()
    connector = FHIRConnector(event_bus)
    
    with pytest.raises(ConnectorError) as exc_info:
        connector.read_patient("non-existent")
    
    assert "not found" in str(exc_info.value)
    assert len(event_bus.published_events) == 1
    assert event_bus.published_events[0].topic == EventTopic.CONNECTOR_READ_FAILURE
    assert event_bus.published_events[0].payload["resource_path"] == "Patient/non-existent"


def test_medical_mqtt_connector_subscribe_readonly():
    event_bus = MockEventBus()
    connector = MedicalMQTTConnector(event_bus)
    
    connector.subscribe("hospital/ward1/ventilator/vitals")
    
    assert "hospital/ward1/ventilator/vitals" in connector.get_subscriptions()
    assert len(event_bus.published_events) == 1
    assert event_bus.published_events[0].topic == EventTopic.CONNECTOR_READ_SUCCESS
    assert event_bus.published_events[0].payload["action"] == "subscribe"


def test_medical_mqtt_connector_read_vitals_success():
    event_bus = MockEventBus()
    connector = MedicalMQTTConnector(event_bus)
    
    connector.subscribe("hospital/ward1/ventilator/vitals")
    event_bus.published_events.clear()
    
    result = connector.read_vitals("hospital/ward1/ventilator/vitals")
    
    assert result["topic"] == "hospital/ward1/ventilator/vitals"
    assert "measurements" in result["payload"]
    assert len(event_bus.published_events) == 1
    assert event_bus.published_events[0].topic == EventTopic.CONNECTOR_READ_SUCCESS
    assert event_bus.published_events[0].payload["action"] == "read"


def test_connectors_publish_read_events_to_event_bus():
    event_bus = MockEventBus()
    fhir_connector = FHIRConnector(event_bus)
    mqtt_connector = MedicalMQTTConnector(event_bus)
    
    fhir_connector.read_patient("pat-001")
    mqtt_connector.subscribe("hospital/ward1/monitor/patient/pat-001/vitals")
    mqtt_connector.read_vitals("hospital/ward1/monitor/patient/pat-001/vitals")
    
    success_events = [e for e in event_bus.published_events if e.topic == EventTopic.CONNECTOR_READ_SUCCESS]
    assert len(success_events) == 3


def test_connectors_have_no_write_methods():
    fhir_connector = FHIRConnector(MockEventBus())
    mqtt_connector = MedicalMQTTConnector(MockEventBus())
    
    fhir_methods = [m for m in dir(fhir_connector) if not m.startswith("_")]
    mqtt_methods = [m for m in dir(mqtt_connector) if not m.startswith("_")]
    
    forbidden = {"write", "publish", "update", "post", "put", "delete", "create", "modify"}
    
    for method in fhir_methods:
        assert method.lower() not in forbidden, f"FHIRConnector has forbidden method: {method}"
    
    for method in mqtt_methods:
        assert method.lower() not in forbidden, f"MedicalMQTTConnector has forbidden method: {method}"