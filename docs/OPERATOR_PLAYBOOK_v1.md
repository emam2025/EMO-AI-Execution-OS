# Operator Playbook v1 — Quick Reference  # LAW-5 # LAW-12

**Audience:** New operators | **⏱️ Time-to-competency:** ≤15 minutes

---

## 1. What Is This System?

A DAG (Directed Acyclic Graph) execution engine. Workflows are modeled as
DAGs — each node is a task, edges define dependencies. You monitor and
control these DAGs through the Operator UI.

---

## 2. Access

| URL | Purpose |
|-----|---------|
| `http://localhost:8080/dashboard` | Cluster health, active DAGs, worker status |
| `http://localhost:8080/trace/<id>` | Chronological timeline of a specific execution |
| `http://localhost:8080/replay/<id>` | Re-run a past execution in deterministic mode |
| `http://localhost:8080/actions` | Pause / Resume / Force Retry |

---

## 3. Core States

| State | Meaning | Action |
|-------|---------|--------|
| **RUNNING** | DAG is executing | Monitor |
| **COMPLETED** | Success | None needed |
| **FAILED** | Node failed | Force Retry (after auto-retries exhausted) |
| **PAUSED** | Suspended by operator | Resume when ready |
| **RETRYING** | Auto-retry in progress | Wait |
| **CANCELLED** | Aborted | Investigate root cause |

---

## 4. Actions

### Pause
- **When:** DAG is consuming resources or needs inspection
- **How:** `/actions` → enter execution ID → **Pause** → confirm

### Resume
- **When:** Paused DAG is ready to continue
- **How:** `/actions` → enter execution ID → **Resume**

### Force Retry
- **When:** DAG FAILED and auto-retries exhausted
- **How:** `/actions` → enter execution ID → **Force Retry**
- ⚠️ Do NOT use while DAG is RUNNING or RETRYING

---

## 5. Reading a Trace

Trace page shows a timeline:
```
1. dag_001 → pending_to_running
2. node_a  → running_to_completed
3. node_b  → running_to_failed  ← FAILURE
4. dag_001 → running_to_failed
```

- **Green** = successful transitions
- **Red** = failures
- Each trace has an `operator_trace_id` for audit linkage

---

## 6. Common Issues

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| UI not loading | Server not running | `python3 frontend/minimal/app.py` |
| Action fails | Wrong execution ID | Check `/dashboard` for active IDs |
| DAG stuck in RUNNING | Worker unavailable | Check worker topology on dashboard |
| Trust Score low | Post-session feedback | Report in survey |

---

## 7. Checklist (First Session)

- [ ] Open dashboard — confirm cluster health is green
- [ ] Find a DAG in RUNNING state
- [ ] Open its trace — identify the latest event
- [ ] Pause and resume the DAG
- [ ] Locate the `operator_trace_id` on any action
- [ ] Find the relevant entry in PILOT_ONBOARDING.md for next steps

---

*If this playbook takes >15 minutes to work through, file a feedback issue.*
