# Pilot Onboarding Guide — Emo-AI Operator  # LAW-5 # LAW-12

**Version:** 4.10.1-human-validated | **Audience:** Operator Pilot Users (≤3)

---

## 1. Accessing the Operator UI

Open your browser and go to:

```
http://localhost:8080/dashboard
```

You will see:
- **Cluster Health** — overall runtime status
- **Active DAGs** — currently running or pending workflows
- **Worker Topology** — node health and assignments
- **Operator Action Log** — recent actions taken by operators

---

## 2. Understanding Basic States

| State | Meaning | What to do |
|-------|---------|------------|
| **RUNNING** | DAG is executing normally | Monitor progress |
| **COMPLETED** | DAG finished successfully | ✓ No action needed |
| **FAILED** | A node in the DAG failed | Consider Retry (see §3) |
| **PAUSED** | Execution was paused by operator | Resume when ready |
| **RETRYING** | System is automatically retrying | Wait — do not force-retry |
| **CANCELLED** | DAG was cancelled | Investigate root cause |

---

## 3. Using Operator Actions

### Pause
- **When:** A DAG is consuming too many resources, or you need to inspect mid-flight
- **How:** Go to `/actions`, enter the execution ID, click **Pause**
- **Effect:** All running nodes complete their current task, then stop
- **Confirmation:** You will be asked to confirm before the action is sent

### Resume
- **When:** You have reviewed a paused DAG and want it to continue
- **How:** Go to `/actions`, enter the same execution ID, click **Resume**
- **Effect:** Nodes pick up from where they paused
- **Safety:** Each resume carries a unique `operator_trace_id` for audit

### Force Retry
- **When:** A DAG has FAILED and automatic retries have been exhausted
- **How:** Go to `/actions`, enter the execution ID, click **Force Retry**
- **Do NOT use if:** The DAG is still running or retrying automatically
- **Effect:** The entire DAG is re-submitted from the last checkpoint

---

## 4. Reading the Trace Explorer

The Trace Explorer (`/trace/<id>`) shows a chronological timeline of events:

```
1. dag_001 → pending_to_running
2. node_a → running_to_completed
3. node_b → running_to_failed  ← THIS IS THE FAILURE
4. dag_001 → running_to_failed
```

- **Green** events = successful transitions
- **Red** events = failures
- The `operator_trace_id` at the top links back to who triggered the action

**Time-to-first-insight goal:** You should be able to find a failure within **30 seconds** of opening the trace.

---

## 5. Who to Contact

| Issue | Contact |
|-------|---------|
| UI not loading | Check the server is running: `python3 frontend/minimal/app.py` |
| Action failed with error | Note the `operator_trace_id` and report to your lead |
| Trust Score < 3/5 | Report in the post-session survey |
| Anything else | Open a ticket with the full trace ID |

---

**Pilot Session Checklist:**
- [ ] Can access the dashboard
- [ ] Can find a trace by ID
- [ ] Can pause and resume an execution
- [ ] Can identify a failed node in the timeline
- [ ] Knows who to contact for help

*This guide is ≤5 pages. If you can follow every step in under 10 minutes, the onboarding is successful.*
