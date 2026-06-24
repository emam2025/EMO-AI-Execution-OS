# EMO AI — User Guide

## User Guide v1.0

> **Version:** 1.0.0-RC18
> **Last Updated:** 2026-06-24

---

## Overview

EMO AI Execution OS is an Industrial AI Execution Operating System. This guide covers the basic usage patterns for interacting with the system.

---

## Authentication

### Login

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "your-username",
    "password": "your-password"
  }'
```

Response:
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 7200
}
```

### Using the Token

```bash
curl -H "Authorization: Bearer eyJ..." \
  http://localhost:8000/api/agents
```

### Refresh Token

```bash
curl -X POST http://localhost:8000/api/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "eyJ..."}'
```

---

## Agents

### List Agents

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/agents
```

### Create Agent

```bash
curl -X POST http://localhost:8000/api/agents \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Quality Inspector",
    "role": "manufacturing_inspector",
    "description": "Monitors product quality on production line"
  }'
```

### Execute Agent

```bash
curl -X POST http://localhost:8000/api/agents/{agent_id}/execute \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "task": "Inspect batch #12345",
    "parameters": {
      "line": "A1",
      "sample_size": 10
    }
  }'
```

---

## Workflows

### Create Workflow

```bash
curl -X POST http://localhost:8000/api/workflows \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Quality Check Pipeline",
    "nodes": [
      {"id": "inspect", "tool": "quality_inspector"},
      {"id": "report", "tool": "report_generator", "depends_on": ["inspect"]}
    ]
  }'
```

### Execute Workflow

```bash
curl -X POST http://localhost:8000/api/workflows/{workflow_id}/execute \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"inputs": {"batch_id": "12345"}}'
```

---

## Industrial Connectors

### Manufacturing (OPC-UA)

```python
from core.connectors.manufacturing.opcua_connector import OPCUAConnector

connector = OPCUAConnector(endpoint="opc.tcp://factory:4840")
await connector.connect()

# Read tags
values = await connector.read_tags([
    "ns=2;s=Temperature",
    "ns=2;s=Pressure"
])
```

### Energy (SCADA)

```python
from core.connectors.energy.scada_connector import SCADAConnector

connector = SCADAConnector(host="scada.local", port=502)
await connector.connect()

# Read registers
data = await connector.read_registers(start=0, count=10)
```

### Water (Modbus)

```python
from core.connectors.water.water_modbus_connector import WaterModbusConnector

connector = WaterModbusConnector(host="plc.local", port=502)
await connector.connect()

# Read holding registers
values = await connector.read_holding_registers(address=100, count=5)
```

---

## Memory System

### Store Memory

```python
from core.memory import ProjectMemory

memory = ProjectMemory(memory_hierarchy=hierarchy)

# Store a memory entry
memory.store(
    project_id="factory-line-a",
    key="maintenance_log",
    payload={"event": "bearing replaced", "date": "2026-06-24"},
    ttl_seconds=86400  # 24 hours
)
```

### Retrieve Memory

```python
entry = memory.retrieve(
    project_id="factory-line-a",
    key="maintenance_log"
)
print(entry.payload)
```

### Search Memory

```python
results = memory.search(
    project_id="factory-line-a",
    query="bearing",
    limit=10
)
```

---

## Governance

### Check Permissions

```python
from core.security.rbac import get_rbac

rbac = get_rbac()
decision = rbac.check(
    role=user.role,
    resource="workflow",
    action="execute",
    scope=tenant_id
)

if decision.allowed:
    # Proceed
    pass
```

### View Audit Trail

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/audit?action=workflow.execute&limit=50"
```

---

## Settings

### Configure LLM Provider

```bash
curl -X PUT http://localhost:8000/api/settings/llm \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "openrouter",
    "model": "meta-llama/llama-3.3-70b-instruct",
    "api_key": "sk-or-..."
  }'
```

### Test Connection

```bash
curl -X POST http://localhost:8000/api/settings/test-connection \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"provider": "openrouter"}'
```

---

## Observability

### Health Check

```bash
curl http://localhost:8000/health
```

### Metrics

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/observability/metrics
```

### Distributed Traces

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/observability/traces?limit=20"
```

---

## Safety Considerations

### Approval Gates

Critical operations require human approval:

```python
from core.runtime.autonomy.approval_gate import ApprovalGate

gate = ApprovalGate()

# Request approval for critical action
approval = await gate.request(
    action="valve_override",
    resource="water_treatment_plant_1",
    reason="Emergency maintenance required",
    requested_by="operator_123"
)

# Wait for approval
if await gate.wait_for_approval(approval.id, timeout=300):
    # Execute the action
    pass
```

### Safety Gates (Industrial)

Each industrial sector has safety gates:

```python
from core.governance.water_policies import WaterSafetyGate

gate = WaterSafetyGate()

# Evaluate action against safety policies
decision = gate.evaluate(
    action_type="PUMP_SHUTDOWN",
    trust_level=TrustLevel.HIGH,
    context={"plant_id": "treatment_1"}
)

if decision.allowed:
    # Safe to proceed
    pass
```

---

## Troubleshooting

### Common Issues

#### Authentication Failed
- Verify JWT secret is set: `echo $EMO_JWT_SECRET`
- Check token expiry (2 hours default)
- Ensure `EMO_AUTH_MODE=enforced` in production

#### Agent Execution Failed
- Check agent status: `GET /api/agents/{id}`
- Review audit trail for errors
- Verify required tools are registered

#### Workflow Validation Failed
- Check for cycles in DAG
- Ensure all tool references exist
- Verify required parameters are provided

---

## Next Steps

- [Installation Guide](INSTALL_GUIDE.md) — Setup details
- [Architecture Reference](EMO_AI_MASTER_ARCHITECTURE_REFERENCE.md) — System design
- [Development Plan](../EMO_AI_DEVELOPMENT_PLAN.md) — Roadmap
- [API Reference](runtime_api_reference.md) — Full API docs
