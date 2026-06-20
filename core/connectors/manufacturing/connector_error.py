"""Connector Error — custom exception for industrial connector failures.

Ref: RC17.1.4 — Manufacturing Connectors (Read-Only V1)
"""


class ConnectorError(Exception):
    """Raised when an industrial connector operation fails.

    Attributes:
        connector_type: Type of connector (opcua, mqtt, modbus).
        message: Human-readable error description.
        node_id: Optional node/topic that caused the failure.
    """

    def __init__(
        self,
        message: str,
        connector_type: str = "unknown",
        node_id: str = "",
    ) -> None:
        self.connector_type = connector_type
        self.node_id = node_id
        super().__init__(message)
