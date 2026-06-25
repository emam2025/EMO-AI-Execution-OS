# 🤝 EMO AI Contribution Guide

Welcome to the EMO AI contribution guide. Please read this entire guide before starting any contribution.

---

## 📋 Before Starting

Before contributing, make sure you understand the project's architecture:

- 📖 Read [DEVELOPER.md](DEVELOPER.md) — comprehensive technical guide
- 🏗️ Read [ARCHITECTURE_DESIGN.md](docs/architecture/) — architectural design
- 📐 Read [SOURCE_OF_TRUTH.md](docs/SOURCE_OF_TRUTH.md) — trust hierarchy and documentation policy
- 🗺️ Read [REPOSITORY_STRUCTURE_MAP.md](docs/REPOSITORY_STRUCTURE_MAP.md) — repository structure map
- ⚖️ Understand **Architecture Canon** (LAW 1-27) — strict architectural rules

> ⚠️ **Strict Warning**: Failure to understand the architectural rules may result in your Pull Request being rejected.

---

## 🚀 Setting Up the Development Environment

### Prerequisites

- Python 3.14+
- pip (latest version)
- git

### Setup Steps

```bash
# 1. Clone the project (Fork first)
git clone https://github.com/YOUR-USERNAME/emo-ai.git
cd emo-ai

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# or
venv\Scripts\activate  # Windows

# 3. Install requirements
pip install -r requirements.txt

# 4. Set up environment variables
cp .env.example .env
# Edit .env with your own keys

# 5. Run tests to verify the environment
python -m pytest tests/ -v
```

---

## 📝 Code Standards

### Code Style

- **PEP 8**: Follow official Python standards
- **Type Hints**: Use type annotations for all functions
- **Docstrings**: Use Google Style Docstrings

```python
def example_function(param1: str, param2: int) -> bool:
    """Brief function description.

    Args:
        param1: Description of param1.
        param2: Description of param2.

    Returns:
        bool: Description of the return value.

    Raises:
        ValueError: If param1 is empty.
    """
    pass
```

### Strict Rules

- ❌ **No circular imports** — Use TYPE_CHECKING for circular imports
- ❌ **No hardcoded secrets** — Use environment variables
- ✅ **Test coverage ≥ 80%** — Every new code requires tests
- ✅ **No modification of core/runtime/** without prior review

---

## 🏗️ Architectural Rules (CRITICAL)

> ⚠️ **These rules are mandatory.** Any violation means immediate PR rejection.

### LAW 1: ExecutionEngine Isolation

```python
# ✅ Correct
from core.execution_governor import ExecutionGovernor

# ❌ Incorrect
from core.runtime.execution_engine import ExecutionEngine  # FORBIDDEN
```

### LAW 13: CompositionRoot Only

```python
# ✅ Correct
def create_service() -> MyService:
    return MyService(dep1, dep2)

# ❌ Incorrect
service = MyService()  # FORBIDDEN outside CompositionRoot
```

### LAW 14-16: CodeGraph Boundaries

- No modification of `core/interfaces/` directly without supervisor notification
- No adding imports from `core.runtime.*` in `core/interfaces/*`

### LAW 20-22: Failure Propagation

- Every service must have a `health_check()` method
- Do not raise exceptions from `health_check()`

### LAW 23-27: Service Ownership

- Each service is responsible only for its scope
- No direct cross-service calls

### Additional Rules

- ** LAW 10**: Do not assume Workers are trustworthy
- **LAW 28**: Do not rely on cron jobs running
- **LAW 35-37**: No Arabic content in core/

> 📖 See [DEVELOPER.md](DEVELOPER.md) for full details of each law.

---

## 🧪 Tests

### Running Tests

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific tests
python -m pytest tests/test_workflow_v2.py -v

# With coverage report
python -m pytest tests/ --cov=core --cov-report=html

# Open coverage report
open htmlcov/index.html
```

### Verify Isolation Compliance (Mandatory)

```bash
# Run emo-guard to verify architectural rules
python -m core.tools.emo_guard --ci

# Or
emo-guard --update-snapshot
```

### Test Acceptance Criteria

- ✅ All existing tests remain PASS
- ✅ No new tests fail
- ✅ Test coverage ≥ 80% for new code
- ✅ No `print()` in production tests

---

## 📤 Pull Request Process

### 1. Fork and Clone

```bash
# Fork the project from GitHub
# Then clone
git clone https://github.com/YOUR-USERNAME/emo-ai.git
cd emo-ai
```

### 2. Create a New Branch

```bash
# Make sure you're on main
git checkout main

# Create a new branch
git checkout -b feature/your-feature-name

# Or
git checkout -b fix/bug-description
```

### 3. Write Code and Tests

```python
# Example: Adding a new feature

# 1. Add the code in the appropriate location
# 2. Add new tests
# 3. Make sure all tests pass
```

### 4. Verification Before Commit

```bash
# Run all tests
python -m pytest tests/ -v

# Verify architectural rules
python -m core.tools.emo_guard --ci

# Check coverage
python -m pytest tests/ --cov=core --cov-report=term-missing
```

### 5. The Commit

```bash
# Add files
git add .

# Write a descriptive message
git commit -m "feat: add health check endpoint for scheduler

- Add health_check() method to ExecutionScheduler
- Returns dict with status, uptime, active_tasks, queue_depth
- Never raises exceptions (wrapped in try/except)
- Add unit tests for health_check

Refs: #123"
```

### 6. Push and Open PR

```bash
# Push the branch
git push origin feature/your-feature-name

# Open a Pull Request from GitHub
# - Descriptive title
# - Description explains what you did and why
# - Link Issue if applicable
```

### 7. PR Review

- ⏳ Wait for supervisor review
- 🔧 Address any feedback
- ✅ Make sure all tests pass in CI

---

## 🚫 What Not to Do

### ❌ Strict Prohibitions

| Action | Reason | Alternative |
|-------|-------|--------|
| Cross-layer imports | Violates LAW 1 | Use interfaces |
| Modifying `core/runtime/*` | Core Freeze | Consult the supervisor |
| Deleting tests | Coverage regression | Rewrite them |
| Hardcoded secrets | Security vulnerability | Use .env |
| `print()` in production | Data leakage | Use `logging` |
| Modifying `core/interfaces/*` | Violates LAW 14-16 | Consult the supervisor |
| Adding `from core.runtime.*` in interfaces | Violates LAW 14-16 | Use TYPE_CHECKING |

### ❌ Do Not Do

```python
# ❌ Do not do this
from core.runtime.services.scheduler import ExecutionScheduler

# ❌ Do not do this
API_KEY = "sk-1234567890"

# ❌ Do not do this
print(f"Debug: {variable}")

# ❌ Do not do this
def test_something():
    assert True  # Empty test
```

### ✅ Do This Instead

```python
# ✅ Use TYPE_CHECKING
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from core.runtime.services.scheduler import ExecutionScheduler

# ✅ Use environment variables
import os
API_KEY = os.getenv("API_KEY")

# ✅ Use logging
import logging
logger = logging.getLogger(__name__)
logger.debug("Debug: %s", variable)

# ✅ Write real tests
def test_something():
    result = my_function()
    assert result == expected_value
```

---

## 📞 Communication

### Communication Channels

- 🐛 **GitHub Issues**: For bugs and feature requests
- 💬 **GitHub Discussions**: For general questions
- 📧 **Email**: For direct contact

### Reporting Security Issues

> ⚠️ **Do not open a public Issue for security vulnerabilities.**

Send an email to: security@emo-ai.dev

---

## 🏆 Acknowledging Contributors

All contributors will appear in the contributors list in README.md.

---

## 📄 License

By contributing to this project, you agree that your work will be licensed under the [MIT License](LICENSE).

---

**Thank you for contributing to EMO AI! 🚀**
