# EMO SDK Specification

## Overview
The EMO SDK provides a programmatic interface to the Emo Cognitive Orchestration system.
It wraps `EmoRuntimeFacade` and exposes a stable, tenant-isolated, deterministic API.

## Supported Languages
- **Python** (native, first-class)
- **JavaScript/TypeScript** (via REST bridge — future)

---

## Python SDK

### Installation
```bash
pip install emo-sdk
```

### Quick Start
```python
from emo import EMOClient

client = EMOClient(tenant_id="acme")
result = await client.orchestrate("summarize the latest Q3 report")
print(result.status)       # "ok" | "rejected" | "error"
print(result.plan_id)      # SHA-256 plan hash
print(result.trace_id)     # og_<trace_id>
```

### Core API

#### `EMOClient(tenant_id: str, *, strict_mode: bool = False)`
Creates a new client bound to a tenant.

#### `async client.orchestrate(intent: str, context: dict | None = None, constraints: dict | None = None) -> OrchestrationResult`
Submit an intent for cognitive orchestration.
- `intent`: Natural language description of the work.
- `context`: Optional dict with `trace_snippets`, `scope_verified`, etc.
- `constraints`: Optional dict with `max_cost_units`, `max_retries`, etc.

Returns `OrchestrationResult` with:
- `status`: `"ok"`, `"rejected"`, or `"error"`
- `plan_id`: Deterministic SHA-256 hash of the plan
- `trace_id`: Orchestration trace ID (`og_<hex>`)
- `critique`: Validation report from the Critic agent
- `optimized_dag`: Optimized execution DAG (if optimizer ran)
- `error`: Error message (if status is `"error"`)

#### `client.health() -> dict`
Returns orchestration health status:
```json
{"status": "ok", "planner": true, "critic": true, "optimizer": true, ...}
```

#### `client.generate_trace_id(intent: str) -> str`
Generate a deterministic trace ID without submitting.

---

### Error Handling
| Exception | When |
|---|---|
| `EMOAuthError` | Missing or invalid authentication |
| `EMOTenantIsolationError` | Cross-tenant access without scope verification |
| `EMOValidationError` | Intent rejected by Critic agent |
| `EMOOrchestrationError` | Internal orchestration failure |

### Examples

**Submit with context:**
```python
result = await client.orchestrate(
    "refactor module",
    context={"trace_snippets": [{"id": 1, "content": "..."}]},
    constraints={"max_cost_units": "200"},
)
```

**Handle rejection:**
```python
result = await client.orchestrate("")
if result.status == "rejected":
    print("Rejected:", result.critique["violations"])
```

---

## JavaScript SDK (Planned)

```javascript
import { EMOClient } from '@emo-ai/sdk';

const client = new EMOClient({ tenantId: 'acme' });
const result = await client.orchestrate('summarize Q3 report');
console.log(result.status);
```

---

## Contract Compliance
- **Deterministic**: Same `intent` + `tenant_id` → same `plan_id` (SHA-256).
- **Tenant-Isolated**: All requests scoped to `tenant_id`; cross-tenant requires `scope_verified`.
- **Zero-Direct-Access**: SDK communicates only through `EmoRuntimeFacade` — no direct access to `core.*`.
- **Final Delivery v4.14.0-cognitive-validated**
