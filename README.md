<div align="center">

# EMO AI Execution OS

### Industrial AI Execution Operating System

[![Version](https://img.shields.io/badge/version-1.0.0--RC18-blue)]()
[![Tests](https://img.shields.io/badge/tests-4,263-green)]()
[![Python](https://img.shields.io/badge/python-3.12+-blue)]()
[![License](https://img.shields.io/badge/license-Proprietary-red)]()
[![Status](https://img.shields.io/badge/status-Pilot--Baseline-yellow)]()

**A unified AI execution platform for industrial-scale automation, governance, and autonomous operations.**

</div>

---

## Overview

EMO AI Execution OS is an **Industrial AI Execution Operating System** — not a chatbot, not an agent framework, not a workflow tool. It is a unified platform that combines:

- **AI Runtime Execution** — DAG-based task execution with retry, recovery, and replay
- **Agent Intelligence** — Multi-agent lifecycle, cognitive orchestration, sector-specific agents
- **Workflow Orchestration** — DAG optimization, validation, and execution
- **Memory Systems** — Hierarchical memory with semantic retrieval and skill graphs
- **Governance** — Identity, RBAC, audit trails, compliance, safety gates
- **Security** — Default Deny, Human-in-the-Loop, Fernet encryption, rate limiting
- **Industrial Integration** — OPC-UA, SCADA, Modbus, FHIR, Digital Twins
- **Autonomous Operations** — Approval gates, controlled autonomy levels

## Architecture

The system is organized into 10 owned layers:

```
EMO AI Execution OS
│
├── Kernel Layer          Execution Runtime, State Machine, Scheduler, Recovery, Replay, Events
├── Intelligence Layer    Agent OS, Planner, Critic, Optimizer, Multi-Agent Swarm
├── Automation Layer      Workflow OS, Tool Runtime, Tool Synthesis, Computer Use
├── Memory Layer          Hierarchy, Semantic Retrieval, Skill Graph, Context Management
├── Governance Layer      Identity, RBAC, Policy Engine, Audit, Compliance
├── Security Layer        Capability Guard, IO Policy, Secrets Runtime, Rate Limiting
├── Platform Layer        Control Plane, Resource Scheduler, Observability
├── Industrial Layer      Digital Twins, OPC-UA, Modbus, SCADA, Industry Packs
├── Cognitive Layer       Strategic Planning, Reflection Loops, Adaptive Policies
└── Enterprise Layer      Multi-tenancy, Billing, Trace Correlation, Compliance Reporting
```

## Industrial Sectors

EMO AI implements sector-specific extensions over a unified core:

| Sector | Connectors | Digital Twin | Status |
|--------|-----------|--------------|--------|
| Manufacturing | OPC-UA | OEE Engine | Foundation Complete |
| Energy | SCADA, MQTT | EnergyTwin | Foundation Complete |
| Water | SCADA, Modbus | WaterTwin | Foundation Complete |
| Healthcare | FHIR, Medical MQTT | HealthcareTwin | Foundation Complete |

## Key Features

### Execution & Runtime
- DAG-based execution engine with 5 bounded services
- Distributed mesh runtime with service registry
- Replay engine with deterministic recovery
- Resource scheduler with fairness + starvation prevention

### Intelligence & Agents
- Planner / Critic / Optimizer cognitive agents
- Multi-agent swarm coordination
- Sector-specific agents (manufacturing, energy, water, healthcare)
- Approval gates for safety-critical operations

### Memory & Knowledge
- Hierarchical memory (WORKING / SHORT_TERM / LONG_TERM / ARCHIVAL)
- Project Memory with tenant isolation
- Semantic retrieval with Vector DB (Qdrant) support
- Skill graph management

### Governance & Security
- Default Deny capability model
- RBAC with role hierarchy
- Audit trail with SHA-256 chain + HMAC signing
- Fernet authenticated encryption (AES-128-CBC + HMAC-SHA256)
- Rate limiting on auth endpoints
- IEC 62443 / SOC2 readiness (in progress)

### Industrial Integration
- Read-only connectors (write support in development)
- Digital twins with state management + simulation
- Sector-specific safety gates (WHO/EPA/IEC compliance)
- Human approval workflow for all critical operations

## Quick Start

### Prerequisites

- Python 3.12+
- pip / venv
- (Optional) Docker for containerized deployment
- (Optional) PostgreSQL for production (SQLite by default)
- (Optional) Qdrant for vector DB production backend

### Installation

```bash
# Clone
git clone https://github.com/emam2025/EMO-AI-Execution-OS.git
cd EMO-AI-Execution-OS

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your settings (JWT secret, API keys, etc.)

# Run
uvicorn main:app --reload --port 8000
```

### Running Tests

```bash
# Full test suite
pytest tests/ -q

# Collect only (count)
pytest tests/ --collect-only -q | tail -1
```

## Project Status

| Metric | Value |
|--------|-------|
| Version | 1.0.0-RC18 |
| Tests | 4,263 |
| Collection Errors | 0 |
| Python Files (core/) | 493 |
| LOC (core/) | ~88,240 |
| Industrial Sectors | 4 |
| Architecture Layers | 10 |

## Documentation

### Primary References
- [Master Architecture Reference](docs/EMO_AI_MASTER_ARCHITECTURE_REFERENCE.md) — Canonical engineering reference
- [Development Plan](EMO_AI_DEVELOPMENT_PLAN.md) — Roadmap and task tracking
- [Architecture Ownership Map](docs/ARCHITECTURE_OWNERSHIP_MAP.md) — Layer ownership
- [Changelog](CHANGELOG.md) — Version history

### Guides
- [Developer Guide](DEVELOPER.md) — Canon Laws, development rules
- [Contributing](CONTRIBUTING.md) — How to contribute
- [Security Policy](SECURITY.md) — Security principles
- [Installation Guide](docs/INSTALL_GUIDE.md) — Detailed setup

### Audit & Compliance
- [Security Audit Log](docs/audit/RC18_SECURITY_AUDIT_LOG.md) — V-1 to V-6 fixes
- [Pilot Latency Log](docs/audit/RC18_PILOT_LATENCY_LOG.md) — Performance audit
- [Accepted Architectural Debt](docs/ACCEPTED_ARCHITECTURAL_DEBT.md) — AD-001 to AD-012

## Development

### Canon Laws

The project enforces 27 architectural laws (LAW 1-27). Key principles:

- **LAW 10**: No business logic in models
- **LAW 13**: Dependencies injected via constructor
- **LAW 18**: Trace analysis determinism
- **LAW 23-27**: Service mesh ownership and isolation

### Source of Truth Policy

All documentation must follow this priority:

1. Current repository source code
2. Automated tests
3. VERSION and release tags
4. Deployment reports
5. Previous architecture documents

### Branch Strategy

- `main` — Production-ready releases
- `develop` — Active development
- `feat/*` — Feature branches
- `fix/*` — Bug fixes
- `chore/*` — Maintenance

## Roadmap

### Completed (Phase 1: Consolidation)
- ✅ 35+ tasks completed (T-01 to T-14, T-A1 to T-A15)
- ✅ ~6,000 LOC dead code removed
- ✅ Production entry point fixed
- ✅ PostgreSQL backend activated
- ✅ Vector DB abstraction (Qdrant)
- ✅ Rate limiting added
- ✅ CI/CD source-of-truth gates

### In Progress (Phase 2: Critical Gaps)
- 🔄 R2 Memory OS (T-30 Project Memory, T-31 Agent Memory, T-32 Long-Term Memory done — 3/10 components)
- ⏳ R16 Write Support (industrial actuator commands)
- ⏳ Computer Use real implementation
- ⏳ K8s/HA/DR deployment

### Planned (Phase 3-6)
- Generative UI (outperform Notion)
- LLM-driven Tool Synthesis (outperform n8n)
- Strategic Planning (R4 Cognitive OS)
- DCS Integration (Honeywell, Siemens, Emerson, ABB, Yokogawa)
- ERP Integration (SAP, Oracle, Microsoft Dynamics)
- Laboratory Integration (LIMS, gas analysis)
- Full Factory Automation
- Operational AI Assistant

See [Development Plan](EMO_AI_DEVELOPMENT_PLAN.md) for complete roadmap.

## License

**© 2026 Eng. Emam AbdullAziz. All rights reserved.**

This repository and all its contents are the intellectual property of Engineer Emam AbdullAziz. Unauthorized reproduction, distribution, or use is strictly prohibited.

## Contact

- **Author**: Eng. Emam AbdullAziz
- **Repository**: [github.com/emam2025/EMO-AI-Execution-OS](https://github.com/emam2025/EMO-AI-Execution-OS)
- **Issues**: [GitHub Issues](https://github.com/emam2025/EMO-AI-Execution-OS/issues)

---

<div align="center">

**Built for industrial-scale AI execution with governance-first principles.**

</div>
