# 📚 EMO AI — Project Index

> Comprehensive project index — Quick guide for any new developer

---

## Overview

| Property | Value |
|----------|-------|
| **Name** | EMO AI Execution OS |
| **Description** | AI operating system for distributed execution |
| **Current Version** | v1.0.0 (RC16.6) |
| **Project Status** | Production-Ready |
| **Language** | Python 3.14+ |
| **Framework** | FastAPI |
| **License** | MIT |

---

## Project Structure

```
Emo-AI/
├── 📄 main.py                    # Main entry point
├── 📄 brain.py                   # LLM interface (4 providers)
├── 📄 agent.py                   # Agent system
├── 📄 requirements.txt           # Requirements
├── 📄 Dockerfile                 # Docker image
├── 📄 docker-compose.yml         # Docker configuration
├── 📄 .env.example               # Environment variables template
├── 📄 README.md                  # Main documentation
├── 📄 CONTRIBUTING.md            # Contribution guide
├── 📄 PROJECT_INDEX.md           # This file
├── 📄 DEVELOPER.md               # Technical guide
├── 📄 LICENSE                    # License
├── 📄 VERSION                    # Project version
│
├── 📁 core/                      # Core kernel (417 files)
├── 📁 routers/                   # API layer (14 files)
├── 📁 tests/                     # Tests (178 files)
├── 📁 docs/                      # Documentation (33 files)
├── 📁 scripts/                   # Scripts (132 files)
├── 📁 releases/                  # Releases (1172 files)
├── 📁 middleware/                 # Middleware layer
├── 📁 simulation_lab/            # Simulation lab
├── 📁 .github/workflows/         # CI/CD
└── 📁 helm/                      # Kubernetes Helm
```

---

## Main Files

| File | Description | Importance |
|------|-------------|------------|
| `main.py` | Entry point — FastAPI app | ⭐⭐⭐ |
| `brain.py` | LLM interface — 4 providers (OpenRouter, Groq, Gemini, Ollama) | ⭐⭐⭐ |
| `agent.py` | Multi-agent system | ⭐⭐⭐ |
| `requirements.txt` | Requirements list | ⭐⭐ |
| `Dockerfile` | Docker image build | ⭐⭐ |
| `.env.example` | Environment variables template | ⭐⭐ |
| `DEVELOPER.md` | Comprehensive technical guide | ⭐⭐⭐ |
| `VERSION` | Current project version | ⭐ |

---

## core/ — Core Kernel

> **417 Python files** — 61 subdirectories

### Main Directories

| Directory | File Count | Description |
|-----------|-----------|-------------|
| `core/runtime/` | 201 | Execution engine and services |
| `core/interfaces/` | 30 | Interfaces and protocols |
| `core/codegraph/` | 25 | Code analysis |
| `core/control_plane/` | 12 | Control plane |
| `core/enterprise/` | 11 | Enterprise features |
| `core/observability/` | 9 | Monitoring and tracing |
| `core/security/` | 8 | Security |
| `core/readiness/` | 7 | Production readiness |
| `core/memory/` | 7 | Memory |
| `core/devex/` | 7 | Developer experience |
| `core/composition/` | 7 | Service composition |
| `core/canon/` | 7 | Architectural rules |
| `core/orchestration/` | 6 | Orchestration |
| `core/models/` | 4 | Models |
| `core/infra/` | 4 | Infrastructure |

### Other Subdirectories

```
core/
├── adapters/          # Adapters
├── agent_teams/       # Agent teams
├── agents/            # Agents
├── applications/      # Applications
├── autonomous_control/ # Autonomous control
├── autonomy/          # Autonomy
├── canvas/            # Canvas
├── chaos/             # Chaos engineering
├── cli/               # Command line interface
├── cloud/             # Cloud
├── cognition/         # Cognition
├── command_center/    # Command center
├── communication_hub/ # Communication hub
├── connector_cert/    # Connector certification
├── connectors/        # Connectors
├── data_fabric/       # Data fabric
├── db.py              # Database
├── deployment/        # Deployment
├── devops/            # DevOps
├── digital_twin_platform/ # Digital twin platform
├── digital_twin_v2/   # Digital twin v2
├── enterprise_memory/ # Enterprise memory
├── execution_governor/ # Execution governor
├── generative_ui/     # Generative UI
├── hardening/         # Hardening
├── human_governance/  # Human governance
├── human_twin/        # Human twin
├── industry_framework/ # Industry framework
├── industry_profiles/ # Sector profiles
├── knowledge_graph/   # Knowledge graph
├── knowledge_os/      # Knowledge OS
├── marketplace/       # Marketplace
├── projectos/         # Project OS
├── recovery/          # Recovery
├── release/           # Release
├── sandbox/           # Sandbox
├── security/          # Security
├── skill_factory/     # Skill factory
├── threat_intel/      # Threat intelligence
├── ui_marketplace/    # UI marketplace
├── ui_schema/         # UI schema
├── workflow_os/       # Workflow OS
├── workflow_runtime_v2/ # Workflow runtime v2
└── workspace_intelligence/ # Workspace intelligence
```

---

## routers/ — API Layer

> **14 files** — FastAPI Routers

| File | Description |
|------|-------------|
| `routers/auth.py` | Authentication (signup, login, verify) |
| `routers/runtime_api.py` | Execution API |
| `routers/project.py` | Project management |
| `routers/settings.py` | Settings |
| `routers/chat.py` | Chat |
| `routers/conversations.py` | Conversations |
| `routers/history.py` | History |
| `routers/tasks.py` | Tasks |
| `routers/ai.py` | Artificial intelligence |
| `routers/stream.py` | Live streaming |
| `routers/observability.py` | Monitoring |
| `routers/e2e.py` | End-to-end tests |

---

## tests/ — Tests

> **178 files** — Comprehensive tests

### Test Categories

| Category | File Count | Description |
|----------|-----------|-------------|
| `tests/test_*.py` | ~50 | Unit tests |
| `tests/phase*.py` | ~80 | Phase tests |
| `tests/red_team/` | ~5 | Security tests |
| `tests/test_security_*.py` | ~10 | Critical security tests |
| `tests/test_workflow_*.py` | ~8 | Workflow tests |

### Running Tests

```bash
# All tests
python -m pytest tests/ -v

# Specific tests
python -m pytest tests/test_service_isolation.py -v

# With coverage
python -m pytest tests/ --cov=core --cov-report=html
```

---

## docs/ — Documentation

> **33 files** — Comprehensive documentation

### Main Documents

| File | Description |
|------|-------------|
| `docs/INDEX.md` | Documentation index |
| `docs/DEVELOPER.md` | Technical guide |
| `docs/architecture/` | Architectural design |
| `docs/api/` | API Reference |
| `docs/sdk/` | Developer guide |
| `docs/security/` | Security model |
| `docs/deployment/` | Deployment guides |
| `docs/testing.md` | Test log |

---

## scripts/ — Automation

> **132 files** — Helper scripts

### Script Categories

| Category | Description |
|----------|-------------|
| `scripts/setup/` | Environment setup |
| `scripts/deploy/` | Project deployment |
| `scripts/test/` | Running tests |
| `scripts/build/` | Building project |
| `scripts/ci/` | CI/CD automation |

---

## releases/ — Releases

> **1172 files** — Project releases

### Main Releases

| Version | Status | Description |
|---------|--------|-------------|
| RC12 | ✅ COMPLETED | Foundation |
| RC13 | ✅ COMPLETED | Cognitive Layer |
| RC14 | ✅ COMPLETED | Workflow Intelligence |
| RC15 | ✅ COMPLETED | Enterprise Platform |
| RC16 | ✅ COMPLETED | Generative Interface OS |
| RC16.6 | ✅ COMPLETED | Knowledge Freeze |
| RC17 | 📋 PLANNED | Domain Intelligence |

---

## Project Statistics

| Statistic | Value |
|-----------|-------|
| **Total Python Files** | 742 |
| **Total Lines of Code** | 161,371 |
| **core/ files** | 417 |
| **routers/ files** | 14 |
| **tests/ files** | 178 |
| **docs/ files** | 33 |
| **scripts/ files** | 132 |
| **releases/ files** | 1,172 |
| **Test Count** | 1,667+ |
| **Success Rate** | 100% |
| **Endpoints** | 290+ |

---

## Quick Links

### Important Documents

- 📖 [README.md](README.md) — Overview
- 🔧 [DEVELOPER.md](DEVELOPER.md) — Technical guide
- 🏗️ [docs/architecture/](docs/architecture/) — Architectural design
- 📡 [docs/api/](docs/api/) — API Reference
- 🔒 [docs/security/](docs/security/) — Security
- 🚀 [docs/deployment/](docs/deployment/) — Deployment
- 🧪 [docs/testing.md](docs/testing.md) — Tests
- 🤝 [CONTRIBUTING.md](CONTRIBUTING.md) — Contribution guide

### Important Scripts

```bash
# Environment setup
python setup.py

# Run server
python main.py

# Quick tests
python -m pytest tests/test_service_isolation.py -v

# Verify architectural rules
python -m core.tools.emo_guard --ci
```

### Common Commands

```bash
# Build Docker
docker build -t emo-ai:latest .

# Run container
docker run -p 8080:8080 --env-file .env emo-ai:latest

# Deploy to Kubernetes
helm install emo-ai ./helm/emo-ai
```

---

**Last Updated**: 2026-06-12
