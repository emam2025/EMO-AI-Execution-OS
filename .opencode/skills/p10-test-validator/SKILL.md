---
name: p10-test-validator
description: >
  Use when running tests, debugging test failures, or verifying test coverage.
  Ensures all P10 release tests pass (20/20) and no core imports exist in test files.
---

# P10 Test Validator

## Commands
- `npm test` — Run all tests from emo-desktop/
- `npx vitest run tests/release/` — Run only P10 release tests
- `npx vitest run tests/release/test_channel_promotion.ts` — Single test file

## Required pass rates
- All P10 tests: 20/20 minimum (5 files × 5 tests)
- Total project: 561/561 (74 test files)

## Validation checklist before PR
1. Run `npm test` — ALL pass
2. Check core imports: `rg "from '(\\.\\./)*core/|from '(\\.\\.)*/releases/" tests/release/`
3. Check all 5 test files exist in `tests/release/`
