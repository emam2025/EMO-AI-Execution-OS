# Source of Truth Policy

## Trust Hierarchy

The following order defines the authority of information sources in this repository.
Higher-ranked sources override lower ones in case of conflict.

| Rank | Source | Description |
|------|--------|-------------|
| 1 | **Code** | The actual source code in the repository. This is the highest authority. |
| 2 | **Tests** | Automated tests verify what actually works. Code without tests is unverified. |
| 3 | **VERSION** | The [VERSION](../VERSION) file defines the current release number. |
| 4 | **Git tags** | Release tags (e.g., `v1.0.0-RC18-BASELINE`) are immutable snapshots. |
| 5 | **Deployment reports** | Verified deployment state (e.g., [PILOT_DEPLOYMENT_REPORT.md](PILOT_DEPLOYMENT_REPORT.md)). |
| 6 | **Architecture docs** | Design documents and architecture references. |
| 7 | **Old discussions** | Historical conversations, notes, and prior documentation. |

## Rules

1. **Code over docs**: If documentation contradicts the code, the code wins.
2. **Tests over speculation**: No capability is considered implemented unless backed by tests.
3. **VERSION is truth**: The VERSION file is the single source for release numbering.
4. **Tags are frozen**: Git tags must never be moved or deleted once created.
5. **Deployment reports reflect reality**: Only verified deployment states are recorded.
6. **Architecture docs guide**: Architecture documents describe intent, not necessarily current state.
7. **Discussions are reference**: Historical discussions inform but do not override current implementation.

## Why This Policy Exists

This policy prevents situations where:

- Old reports claim a feature is broken when it has since been fixed.
- Architecture documents describe a future state as if it exists today.
- Historical discussions override current source code reality.

**Example:** A report from 3 months ago stating "Computer Use 0%" is overridden by current code and tests showing Computer Use functional at 100%.

## Enforcement

- Every PR must be consistent with the trust hierarchy.
- Documentation updates must reflect current code reality.
- Old documents must not be deleted but must be clearly marked as historical.
