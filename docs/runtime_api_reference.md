# Runtime API Reference

Auto-generated from `core/interfaces/` protocols and `core/runtime/facade.py`.

---

## EmoRuntimeFacade

Primary entry point. Injected via constructor with all orchestration and memory agents.

**Location:** `core/runtime/facade.py`

### Constructor Parameters
| Parameter | Type | Default | Description |
|---|---|---|---|
| `planner_agent` | `IPlannerAgent` | `None` | DAG planner |
| `critic_agent` | `ICriticAgent` | `None` | Plan critic |
| `optimizer_agent` | `IOptimizerAgent` | `None` | DAG optimizer |
| `orchestration_state_machine` | `OrchestrationStateMachine` | `None` | State machine |
| `orchestration_trace_correlator` | `OrchestrationTraceCorrelator` | `None` | Trace correlation |
| `memory_store` | `MemoryHierarchy` | `None` | Memory hierarchy |
| `context_compiler` | `ContextCompiler` | `None` | Context compilation |
| `skill_graph_manager` | `SkillGraphManager` | `None` | Skill graph |
| `memory_state_machine` | `MemoryStateMachine` | `None` | Memory state machine |
| `memory_trace_correlator` | `CognitiveTraceCorrelator` | `None` | Memory trace |

### Methods

#### `async orchestrate(intent, tenant_id, context_window=None, constraints=None) -> dict`
Submit intent → Plan → Critic → Optimize pipeline.

#### `orchestration_health() -> dict`
Returns health status of all orchestration agents.

#### `memory_store(key, value, tenant_id, ttl=None) -> dict`
Store a value in memory hierarchy.

#### `memory_retrieve(key, tenant_id) -> dict`
Retrieve a value from memory hierarchy.

#### `memory_prune(tenant_id) -> dict`
Prune expired entries.

#### `compile_context(intent, tenant_id, memory_context=None) -> dict`
Compile context with budget enforcement.

---

## Protocol Interfaces

### IPlannerAgent
**File:** `protocols/01_cognitive_orchestration_protocols.py`

```python
class IPlannerAgent(Protocol):
    async def synthesize_dag(intent, context, tenant_id, constraints, cognitive_trace_id) -> dict
    async def adapt_on_failure(proposal, feedback, tenant_id, cognitive_trace_id) -> dict
```

### ICriticAgent
```python
class ICriticAgent(Protocol):
    async def evaluate_plan(plan, constraints, tenant_id, cognitive_trace_id) -> dict
    async def reject_with_reason(plan, reason, tenant_id, cognitive_trace_id) -> dict
```

### IOptimizerAgent
```python
class IOptimizerAgent(Protocol):
    async def optimize_execution_graph(dag, constraints, tenant_id, cognitive_trace_id) -> dict
    async def suggest_parallelism(dag, constraints) -> list
```

### IEventBus
**File:** `core/interfaces/event_bus.py`

```python
class IEventBus(Protocol):
    def publish(topic: str, event: dict) -> None
    def subscribe(topic: str, handler: Callable) -> None
    def unsubscribe(topic: str, handler: Callable) -> None
    def get_events(topic: str, limit: int = 10) -> list[dict]
    def get_all_events(limit: int = 50) -> list[dict]
    def clear() -> None
```

### IExecutionEngine
**File:** `core/interfaces/execution_engine.py`

```python
class IExecutionEngine(Protocol):
    async def execute(dag, session_id, strategy, tool_runner) -> dict
    async def plan(nodes) -> list
    async def cancel(exec_id: str) -> None
    async def status(exec_id: str) -> dict
    async def register_tool(spec: dict) -> None
```

### IExecutionDispatcher
**File:** `core/interfaces/dispatcher.py`

```python
class IExecutionDispatcher(Protocol):
    def resolve_tool(name: str) -> Optional[ToolSpec]
    def can_dispatch(name: str) -> bool
    def dispatch_local(node, runner, timeout=300) -> dict
    def dispatch_remote(node, svc_registry) -> dict
    def validate_contract(spec, inputs) -> list
    def validate_output(spec, results) -> list
```

### IExecutionStateStore
**File:** `core/interfaces/state_store.py`

```python
class IExecutionStateStore(Protocol):
    async def get_state(node_id: str) -> Optional[str]
    async def set_state(node_id: str, state: str) -> None
    async def store_trace(session_id, dag, results, status) -> None
    async def save_checkpoint(exec_id, snapshot) -> str
    async def restore_checkpoint(exec_id) -> Optional[dict]
```

### IExecutionRetryHandler
**File:** `core/interfaces/retry.py`

```python
class IExecutionRetryHandler(Protocol):
    def classify_failure(error: Exception) -> str
    def should_retry(node, policy) -> bool
    def compute_backoff(count, policy) -> float
    def handle_exhaustion(node, error) -> dict
    def record_attempt(node, success, duration) -> None
```

### IExecutionLeaseManager
**File:** `core/interfaces/lease.py`

```python
class IExecutionLeaseManager(Protocol):
    def acquire(node, worker, ttl) -> bool
    def release(node, worker) -> None
    def heartbeat(node, worker) -> bool
    def is_expired(node) -> bool
    def owner(node) -> Optional[str]
    def release_all(worker) -> int
```

### IExecutionScheduler
**File:** `core/interfaces/scheduler.py`

```python
class IExecutionScheduler(Protocol):
    def order_levels(dag) -> list[list]
    def select_ready_nodes(dag, in_progress, completed) -> list
    def allocate_worker(node, pool, active) -> Optional[str]
    def estimate_execution_order(dag, strategy) -> list
```

### IDAGOptimizer
**File:** `core/interfaces/execution.py`

```python
class IDAGOptimizer(Protocol):
    def optimize(dag) -> DependencyGraph
```

### ICostTracker, IDAGSizeLimiter, ICheckpointManager
**File:** `core/interfaces/systems.py`

```python
class ICostTracker(Protocol):
    def record_cost(node_id, cost) -> None
    def estimate_cost(node) -> float

class IDAGSizeLimiter(Protocol):
    def check(dag) -> list[dict]

class ICheckpointManager(Protocol):
    def save(session_id, snapshot) -> str
    def restore(ckpt_id) -> Optional[dict]
```

### IContractValidator, IComplianceValidator
**File:** `core/interfaces/governance.py`

```python
class IContractValidator(Protocol):
    def validate_inputs(spec, inputs) -> list
    def validate_outputs(spec, outputs) -> list

class IComplianceValidator(Protocol):
    def verify_frozen_methods(contract) -> list
    def validate_outputs(spec, outputs) -> list
```

---

## Usage Examples

### Python
```python
from core.runtime.facade import EmoRuntimeFacade
from core.orchestration.planner_agent import PlannerAgent
from core.orchestration.critic_agent import CriticAgent

facade = EmoRuntimeFacade(
    planner_agent=PlannerAgent(),
    critic_agent=CriticAgent(),
)
result = await facade.orchestrate("summarize", "tenant_a")
print(result["status"])
```

### CLI
```bash
python scripts/cli/emo_cli.py submit summarize --tenant acme
python scripts/cli/emo_cli.py status
```
