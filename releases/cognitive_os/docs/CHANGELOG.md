# Cognitive OS — Changelog

All notable changes to the EMO Cognitive OS (R4) will be documented here.

## [r4-cognitive-os-v1.0.0] — 2026-05-30

### R4 Cognitive OS — Planning, Reflection & Self-Evaluation

- **StrategicPlanner** (`core/cognitive/planner.py`): `decompose_goal`, `evaluate_feasibility`, `list_active_plans`, `get_plan` — DAG blueprint generation with validator_signature.
- **ReflectionEngine** (`core/cognitive/reflection.py`): `analyze_failure`, `generate_correction`, `list_reflections`, `get_reflection` — severity detection with 10 error patterns.
- **SelfEvaluator** (`core/cognitive/evaluator.py`): `validate_plan_integrity`, `assess_risk`, `list_evaluations`, `get_assessment` — risk scoring capped at 0.95.
- **R2/R3 Read-Only Bridges** (`core/cognitive/bridges.py`): `R2MemoryBridge` + `R3SkillBridge` — zero mutation enforced.
- **Tests**: 91/91 PASS (75 new + 16 foundation).
- **Canon Laws**: LAW-6, LAW-8, LAW-11, LAW-14 enforced.
- **Status**: ✅ IMMUTABLE — CLOSED
