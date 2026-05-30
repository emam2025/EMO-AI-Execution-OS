# C4 Autoscaling Test Harness Specification
# Generated: 2026-05-21T06:49:59.178160Z

## Purpose
Ready-to-run validation harness for Phase F2 Autoscaler infrastructure.
Script: scripts/audit/c4_autoscaling_harness.py

## Validated Behaviors

### 1. Autoscaler.evaluate() Decision Rules
- Scale-up trigger: worker_utilization >= 0.70 OR pending_tasks/workers >= 3
- Scale-down trigger: worker_utilization <= 0.30 (above min_workers)
- Cooldown: 60s between scale events (ScalingDecision.NONE during cooldown)
- Bounds: min_workers prevents scale-down, max_workers prevents scale-up
- Conflicting signals (both up and down) → ScalingDecision.NONE

### 2. RuntimeCoordinator Integration
- evaluate_scaling() delegates to Autoscaler, emits timeline events
- scale_to(N) increases workers via ControlPlaneBrain.state.register_worker()
- scale_to(N) decreases workers via WorkerDrainer.start_drain()
- status_summary() reports autoscaler/drainer/supervisor state

### 3. MetricsStore Readiness
- MetricsStore accepts arbitrary metric names (worker_count, queue_depth, etc.)
- Query with time-range and limit

## Expected Autoscaling Behavior (Once Fully Integrated)
- Automated evaluation loop (recurring timer or event-driven)
- MetricsStore query before evaluate() for live metrics
- Scale execution (not just recommendation): actual worker provisioning
- SLA/latency-based triggers
- Predictive/time-based scaling
- Integration with DAG scheduler for priority-aware scaling

## Current Gaps
- Autoscaler.evaluate() is a stateless function call — no automated recurring evaluation loop
- Autoscaler produces ScalingDecision recommendations but does NOT execute scaling (scale execution is Coordinator's job)
- No automatic MetricsStore integration — evaluate() takes raw floats, caller must query first
- No predictive/time-based autoscaling — only threshold-based reactive scaling
- Cooldown is timer-based (wall clock), not event-based (completion of scale action)
- Scale-up count doubles when pending_tasks > 10 (hardcoded multiplier)
- No SLA/latency-based scaling trigger — only utilization + pending_tasks
- No integration with DAG scheduler — autoscaler doesn't know about DAG structure or node priorities

