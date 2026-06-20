from typing import Dict, Any, List, Optional
from core.interfaces.event_bus import IEventBus
from core.models.event import EventTopic, ExecutionEvent, EventMetadata
from core.connectors.manufacturing.connector_error import ConnectorError


class MedicalMQTTConnector:
    def __init__(self, event_bus: IEventBus, broker_host: str = "mqtt.hospital.local", broker_port: int = 1883):
        self._event_bus = event_bus
        self._broker_host = broker_host
        self._broker_port = broker_port
        self._subscriptions: Dict[str, Dict[str, Any]] = {}
        self._mock_topics = {
            "hospital/ward1/ventilator/vitals": {
                "topic": "hospital/ward1/ventilator/vitals",
                "payload": {
                    "device_id": "VENT-001",
                    "timestamp": "2024-01-15T10:30:00Z",
                    "measurements": {
                        "tidal_volume": 500,
                        "respiratory_rate": 16,
                        "peak_pressure": 25,
                        "peep": 5,
                        "fio2": 0.4,
                    },
                },
            },
            "hospital/ward1/monitor/patient/pat-001/vitals": {
                "topic": "hospital/ward1/monitor/patient/pat-001/vitals",
                "payload": {
                    "patient_id": "pat-001",
                    "timestamp": "2024-01-15T10:30:00Z",
                    "vitals": {
                        "heart_rate": 78,
                        "spo2": 98,
                        "systolic_bp": 120,
                        "diastolic_bp": 80,
                        "temperature": 37.0,
                    },
                },
            },
            "hospital/ward1/infusion_pump/status": {
                "topic": "hospital/ward1/infusion_pump/status",
                "payload": {
                    "device_id": "PUMP-001",
                    "timestamp": "2024-01-15T10:30:00Z",
                    "status": "running",
                    "rate_ml_hr": 50,
                    "volume_infused_ml": 125,
                    "battery_level": 85,
                },
            },
        }

    def _publish_event(self, topic: EventTopic, payload: Dict[str, Any], source: str) -> None:
        event = ExecutionEvent(
            topic=topic,
            payload=payload,
            trace_id="",
            metadata=EventMetadata(source=source),
        )
        self._event_bus.publish(topic, event)

    def subscribe(self, topic: str) -> None:
        if topic not in self._mock_topics:
            self._publish_event(
                EventTopic.CONNECTOR_READ_FAILURE,
                {"topic": topic, "error": "Topic not available"},
                "medical_mqtt_connector",
            )
            raise ConnectorError(f"MQTT topic not available: {topic}", connector_type="mqtt", node_id=topic)
        
        if topic in self._subscriptions:
            return
        
        self._subscriptions[topic] = self._mock_topics[topic]
        
        self._publish_event(
            EventTopic.CONNECTOR_READ_SUCCESS,
            {"topic": topic, "action": "subscribe"},
            "medical_mqtt_connector",
        )

    def read_topic(self, topic: str) -> Dict[str, Any]:
        if topic not in self._subscriptions:
            self._publish_event(
                EventTopic.CONNECTOR_READ_FAILURE,
                {"topic": topic, "error": "Not subscribed to topic"},
                "medical_mqtt_connector",
            )
            raise ConnectorError(f"Not subscribed to topic: {topic}", connector_type="mqtt", node_id=topic)
        
        data = self._subscriptions[topic]
        self._publish_event(
            EventTopic.CONNECTOR_READ_SUCCESS,
            {"topic": topic, "action": "read"},
            "medical_mqtt_connector",
        )
        return data

    def read_vitals(self, topic: str) -> Dict[str, Any]:
        return self.read_topic(topic)

    def get_subscriptions(self) -> List[str]:
        return list(self._subscriptions.keys())

    def list_available_topics(self) -> List[str]:
        return list(self._mock_topics.keys())