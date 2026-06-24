# Contributing to EMO AI Execution OS

> **Version:** 1.0.0-RC18
> **Last Updated:** 2026-06-24

Thank you for your interest in contributing to EMO AI Execution OS. This document outlines the process and standards for contributions.

---

## Getting Started

### Prerequisites

- Python 3.12+
- Git
- Basic understanding of the [Canon Laws](DEVELOPER.md#canon-laws-law-1-27)
- Familiarity with the [Architecture Layers](DEVELOPER.md#architecture-layers)

### Setup

```bash
# Fork and clone
git clone https://github.com/your-username/EMO-AI-Execution-OS.git
cd EMO-AI-Execution-OS

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your settings
```

---

## Development Workflow

### 1. Create a Branch

```bash
git checkout develop
git pull origin develop
git checkout -b feat/your-feature-name
```

**Branch naming:**
- `feat/<scope>-<description>` — New features
- `fix/<scope>-<description>` — Bug fixes
- `chore/<scope>-<description>` — Maintenance
- `docs/<scope>-<description>` — Documentation
- `refactor/<scope>-<description>` — Refactoring
- `test/<scope>-<description>` — Tests

### 2. Make Changes

Follow the [Canon Laws](DEVELOPER.md#canon-laws-law-1-27) and [Development Rules](DEVELOPER.md#development-rules).

**Key requirements:**
- Every component belongs to a defined layer
- All new features require tests
- No `NotImplementedError` in `core/` (use ABC + `@abstractmethod`)
- No hardcoded secrets
- No global mutable state (LAW 11)
- No business logic in models (LAW 10)

### 3. Write Tests

```python
# tests/test_your_feature.py
import pytest
from core.your_module import YourClass


class TestYourFeature:
    def test_basic_functionality(self):
        """Test the happy path."""
        obj = YourClass()
        result = obj.do_something()
        assert result is not None
        assert result.status == "expected"

    def test_edge_case(self):
        """Test edge cases."""
        obj = YourClass()
        result = obj.do_something(extreme_input=True)
        assert result.handled_correctly

    def test_error_handling(self):
        """Test error scenarios."""
        obj = YourClass()
        with pytest.raises(ValueError):
            obj.do_something(invalid=True)
```

### 4. Run Tests

```bash
# Your feature tests
pytest tests/test_your_feature.py -v

# Full suite (ensure no regression)
pytest tests/ -q --tb=no

# Collect only (verify count)
pytest tests/ --collect-only -q | tail -1
```

### 5. Verify Canon Compliance

```bash
# No NotImplementedError in core/
grep -rn "raise NotImplementedError" core/ --include="*.py" | wc -l
# Expected: 0

# No hardcoded secrets
grep -rnE "(password|secret|api_key)\s*=\s*['\"][^'\"]{8,}['\"]" core/
# Expected: (empty)

# Test count consistency
python3 scripts/verify_test_count.py
# Expected: exit 0
```

### 6. Commit Changes

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```bash
git add .
git commit -m "feat(memory): implement Agent Memory with 75 tests (T-31)

- Add AgentMemory class wrapping MemoryHierarchy on AGENT layer
- CRUD: store, retrieve, search, delete
- Integration with SkillGraphManager
- 75 tests across 11 test classes

Task: T-31"
```

### 7. Push and Open PR

```bash
git push origin feat/your-feature-name
```

Open a Pull Request on GitHub with:
- Clear title following Conventional Commits
- Description of changes
- Test output verification
- Link to relevant task/issue

---

## Pull Request Guidelines

### PR Template

```markdown
## Description

Brief description of what this PR does.

## Type of Change

- [ ] New feature (non-breaking change which adds functionality)
- [ ] Bug fix (non-breaking change which fixes an issue)
- [ ] Breaking change (fix or feature that would cause existing functionality to not work as expected)
- [ ] Documentation update
- [ ] Refactoring (no functional changes)

## Task

Reference: T-XX (if applicable)

## Changes

- Change 1
- Change 2

## Verification

```bash
# Test count
$ pytest tests/ --collect-only -q | tail -1
XXXX tests collected

# Your feature tests
$ pytest tests/test_your_feature.py -v
XX passed

# No regression
$ pytest tests/ -q --tb=no | tail -1
XXXX passed, 0 failed

# Canon compliance
$ grep -rn "raise NotImplementedError" core/ --include="*.py" | wc -l
0
```

## Checklist

- [ ] Code follows Canon Laws (LAW 1-27)
- [ ] Tests added for all changes
- [ ] All tests pass (0 failures)
- [ ] No NotImplementedError in core/
- [ ] No hardcoded secrets
- [ ] Documentation updated (CHANGELOG, relevant docs)
- [ ] Commit message follows Conventional Commits
- [ ] Branch is up to date with develop
```

---

## Code Standards

### Python

- Follow PEP 8
- Use type hints everywhere
- Docstrings for all public functions/classes
- Maximum line length: 100 characters

### Example

```python
from typing import Optional, List, Dict, Any
from dataclasses import dataclass


@dataclass(frozen=True)
class ProjectMemoryEntry:
    """A single memory entry in the project namespace.
    
    Attributes:
        project_id: The project this memory belongs to
        key: Unique key within the project
        payload: The memory content
        ttl_seconds: Time to live (None = no expiry)
    """
    project_id: str
    key: str
    payload: Dict[str, Any]
    ttl_seconds: Optional[int] = None


class ProjectMemory:
    """Per-project memory namespace with TTL, isolation, and audit.
    
    Wraps MemoryHierarchy on the PROJECT layer to provide project-scoped
    memory operations with tenant isolation.
    """
    
    def __init__(self, memory_hierarchy: MemoryHierarchy) -> None:
        self._hierarchy = memory_hierarchy
    
    def store(
        self,
        project_id: str,
        key: str,
        payload: Dict[str, Any],
        ttl_seconds: Optional[int] = None
    ) -> str:
        """Store a memory entry.
        
        Args:
            project_id: Project namespace
            key: Unique key within project
            payload: Memory content
            ttl_seconds: Optional TTL
            
        Returns:
            Memory ID
        """
        # Implementation
        pass
```

---

## Testing Standards

### Test Coverage

- All new features require tests
- Minimum 70% line coverage for new code
- Critical paths require E2E tests
- Security features require dedicated security tests

### Test Naming

```python
class TestProjectMemory:
    def test_store_creates_entry(self):
        """Test that store creates a memory entry."""
        pass
    
    def test_retrieve_returns_stored_entry(self):
        """Test that retrieve returns the stored entry."""
        pass
    
    def test_retrieve_returns_none_for_missing_key(self):
        """Test that retrieve returns None for missing key."""
        pass
    
    def test_delete_removes_entry(self):
        """Test that delete removes the entry."""
        pass
```

### Test Categories

| Category | Location | Purpose |
|----------|----------|---------|
| Unit | `tests/test_*.py` | Test individual components |
| Integration | `tests/test_*_integration.py` | Test component interactions |
| E2E | `tests/test_*_e2e.py` | Test full workflows |
| Security | `tests/security/` | Security-specific tests |
| Chaos | `tests/chaos/` | Chaos engineering |
| Load | `tests/load/` | Performance tests |

---

## Architecture Decisions

### When to Create a New Layer

New layers are rare and require:
1. Discussion with architecture team
2. Canon Law update
3. Documentation in Master Architecture Reference

### When to Refactor

Refactor when:
- Code duplication exceeds 100 LOC
- Component doesn't fit existing layer
- Canon Law violation detected
- Dead code accumulates

### When to Add Technical Debt

Document in `docs/ACCEPTED_ARCHITECTURAL_DEBT.md` when:
- Quick fix needed for pilot
- Full solution requires major refactor
- Risk of blocking delivery

---

## Security Considerations

### Before Submitting

- [ ] No hardcoded secrets
- [ ] No sensitive data in logs
- [ ] Authentication required for all endpoints
- [ ] Authorization checked for all operations
- [ ] Input validation on all user inputs
- [ ] SQL injection prevention (use parameterized queries)
- [ ] XSS prevention (sanitize outputs)

### Security Review

All changes to `core/security/` or `core/governance/` require:
1. Additional review by security maintainer
2. Security test coverage
3. Update to security documentation if needed

---

## Getting Help

### Resources

- [Developer Guide](DEVELOPER.md) — Canon Laws, architecture
- [Architecture Reference](docs/EMO_AI_MASTER_ARCHITECTURE_REFERENCE.md)
- [Development Plan](EMO_AI_DEVELOPMENT_PLAN.md) — Task tracking
- [Changelog](CHANGELOG.md) — Recent changes

### Communication

- GitHub Issues — Bug reports, feature requests
- GitHub Discussions — Questions, general discussion
- Pull Request comments — Code-specific discussions

---

## Recognition

Contributors will be recognized in:
- CHANGELOG.md for significant contributions
- README.md contributors section (if applicable)

---

Thank you for contributing to EMO AI Execution OS!
