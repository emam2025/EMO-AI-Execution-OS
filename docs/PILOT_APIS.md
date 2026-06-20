# EMO AI — Pilot APIs Documentation

Industrial APIs for dashboard integration, monitoring systems, and operator workflows.

---

## 1. Manufacturing Scenario APIs

### Start CNC Overheat E2E Scenario

Trigger a full CNC overheat scenario through the LineSupervisorAgent.

**Agent Call:**
```python
from core.agents.manufacturing.line_supervisor import LineSupervisorAgent
from core.models.agent import AgentIdentity

identity = AgentIdentity(
    id="supervisor-01",
    tenant_id="t-1",
    org_id=None,
    name="Line Supervisor",
    agent_type="line_supervisor",
)
agent = LineSupervisorAgent(identity=identity)
agent.activate()

# Read line status (no approval needed)
status = agent.get_line_status("line-A")
# Returns: {"line_id": "line-A", "status": "RUNNING", ...}

# Shutdown line (requires approval)
result = agent.shutdown_line("line-A")
# Returns: {"status": "pending_approval", "request_id": "..."}
```

**JSON Response — Line Status:**
```json
{
  "line_id": "line-A",
  "status": "RUNNING",
  "temperature": 72.5,
  "pressure": 101.3,
  "version": 15,
  "last_updated": "2026-06-14T12:00:00+00:00"
}
```

**JSON Response — Shutdown Request:**
```json
{
  "status": "pending_approval",
  "request_id": "approval-abc-123",
  "agent_id": "supervisor-01",
  "line_id": "line-A",
  "action": "line_shutdown"
}
```

---

## 2. Monitoring APIs

### Query OEE State

```python
from core.agents.manufacturing.oee_monitor_agent import OEEMonitorAgent
from core.industrial.oee_engine import OEECalculator, ProductionMetrics

calculator = OEECalculator()
metrics = ProductionMetrics(
    planned_production_time_minutes=60.0,
    run_time_minutes=50.0,
    total_count=1000,
    good_count=980,
    ideal_run_rate_per_minute=20.0,
)
state = calculator.calculate_oee("cnc-01", metrics)
```

**JSON Response — OEE State:**
```json
{
  "asset_id": "cnc-01",
  "availability_pct": 83.33,
  "performance_pct": 100.0,
  "quality_pct": 98.0,
  "overall_oee_pct": 81.67,
  "timestamp": "2026-06-14T12:00:00+00:00"
}
```

### Query Predictive Alerts

```python
from core.agents.manufacturing.predictive_maintenance_agent import PredictiveMaintenanceAgent

agent = PredictiveMaintenanceAgent(identity=identity, event_bus=event_bus)
agent.activate()

# Alerts generated from CONNECTOR_READ_SUCCESS events
# Check audit trail for recent alerts
alerts = agent.audit.action_log
```

**JSON Response — Predictive Alert:**
```json
{
  "alert_id": "alert-uuid",
  "asset_id": "cnc-01",
  "failure_mode": "overheat",
  "confidence": 0.85,
  "threshold_exceeded": 95.0,
  "current_value": 97.5,
  "timestamp": "2026-06-14T12:00:00+00:00"
}
```

### Query Twin State

```python
from core.industrial.twin_manager import TwinManager

tm = TwinManager()
state = tm.get_twin_state("line-A")
```

**JSON Response — Twin State:**
```json
{
  "asset_id": "line-A",
  "state": {
    "temperature": 72.5,
    "pressure": 101.3,
    "status": "RUNNING"
  },
  "version": 15,
  "last_updated": "2026-06-14T12:00:00+00:00",
  "metadata": {}
}
```

---

## 3. Safety & Approval Flows

### ApprovalManager — Human-in-the-Loop

```python
from core.control_plane.approval_manager import ApprovalManager

am = ApprovalManager()

# Create approval request
request = am.create_request(
    action="line_shutdown",
    requester_id="supervisor-01",
    context={"line_id": "line-A", "reason": "Overheat detected"},
    required_approvers=["operator-01"],
)

# Operator approves
am.approve_request(request.request_id, "operator-01", "Approved for safety")

# Operator rejects
am.reject_request(request.request_id, "operator-01", "Line stabilized")
```

**JSON Response — Approval Request:**
```json
{
  "request_id": "approval-abc-123",
  "action": "line_shutdown",
  "requester_id": "supervisor-01",
  "status": "pending",
  "context": {
    "line_id": "line-A",
    "reason": "Overheat detected"
  },
  "required_approvers": ["operator-01"],
  "created_at": "2026-06-14T12:00:00+00:00"
}
```

### Actions Requiring Human Approval

| Action | Autonomy Level | Description |
|--------|---------------|-------------|
| `line_shutdown` | L2 | Shutdown production line |
| `emergency_stop` | L2 | Emergency stop all operations |
| `quarantine_batch` | L2 | Quarantine quality batch |
| `approve_work_order` | L2 | Approve maintenance work order |
| `reorder_stock` | L2 | Reorder warehouse stock |
| `dispatch_vehicle` | L2 | Dispatch fleet vehicle |
| `override_route` | L2 | Override fleet route |

---

## 4. Event Stream APIs

### Subscribe to Events

```python
from core.runtime.events.memory_bus import InMemoryEventBus
from core.models.event import EventTopic

event_bus = InMemoryEventBus()

async def on_safety_violation(event):
    print(f"SAFETY VIOLATION: {event.payload}")

event_bus.subscribe(EventTopic.SAFETY_VIOLATION, on_safety_violation)
```

### Available Event Topics

| Topic | Description |
|-------|-------------|
| `NODE_STARTED` | Execution node started |
| `NODE_COMPLETED` | Execution node completed |
| `NODE_FAILED` | Execution node failed |
| `TWIN_STATE_UPDATED` | Digital twin state changed |
| `SAFETY_VIOLATION` | Safety limit exceeded |
| `GUARDRAIL_ALERT` | Guardrail drift detected |
| `SECURITY_VIOLATION` | Security policy breach |
| `EXECUTION_STARTED` | Sandbox execution started |
| `EXECUTION_COMPLETED` | Sandbox execution completed |
| `EXECUTION_FAILED` | Sandbox execution failed |
| `OEE_CALCULATED` | OEE metrics calculated |
| `PREDICTIVE_ALERT` | Predictive maintenance alert |
| `QUALITY_LINE_SLOWDOWN_REQUESTED` | Quality slowdown requested |
| `APPROVAL_REQUESTED` | Approval request created |
| `APPROVAL_DECIDED` | Approval request decided |

### Persist Events to Store

```python
from core.runtime.events.store import SQLiteEventStore
from core.models.event import ExecutionEvent

store = SQLiteEventStore("/path/to/events.db")

event = ExecutionEvent(
    topic=EventTopic.OEE_CALCULATED,
    payload={"asset_id": "cnc-01", "oee_pct": 81.67},
    trace_id="oee-calc-001",
)
store.append(event)

# Replay events
events = store.replay(topic=EventTopic.OEE_CALCULATED)
```

---

## 5. Guardrails Configuration

See `core/governance/pilot_guardrails_config.py` for production-ready thresholds:

- **OEE Thresholds:** `overall_oee_pct < 60.0` triggers alert
- **Temperature Limit:** `> 95.0°C` triggers safety violation
- **Vibration Limit:** `> 5.0` triggers predictive alert
- **Defect Threshold:** 3 consecutive defects triggers slowdown request
- **Approval Rules:** All critical actions require human approval

---

## 6. Component Reference

| Component | Module | Description |
|-----------|--------|-------------|
| `LineSupervisorAgent` | `core.agents.manufacturing.line_supervisor` | Production line control |
| `OEECalculator` | `core.industrial.oee_engine` | OEE metrics computation |
| `PredictiveMaintenanceAgent` | `core.agents.manufacturing.predictive_maintenance_agent` | Predictive alerts |
| `QualityInspectorClosedLoop` | `core.agents.manufacturing.quality_inspector_agent` | Quality control |
| `OEEMonitorAgent` | `core.agents.manufacturing.oee_monitor_agent` | OEE dashboard |
| `TwinManager` | `core.industrial.twin_manager` | Digital twin state |
| `DataPipeline` | `core.industrial.data_pipeline` | Connector → Twin ingestion |
| `ApprovalManager` | `core.control_plane.approval_manager` | Human approval workflow |
| `SafetyGate` | `core.governance.safety_gate` | Safety limit enforcement |
| `GuardrailsEngine` | `core.governance.guardrails_engine` | Drift detection |
| `RollbackEngine` | `core.governance.rollback_engine` | Auto-rollback on failure |
| `SandboxExecutor` | `core.runtime.sandbox.sandbox_executor` | Isolated execution |
| `IsolationRuntime` | `core.runtime.isolation.isolation_runtime` | RULE 3 pipeline |
