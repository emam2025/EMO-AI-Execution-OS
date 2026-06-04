---
name: core-freeze-guard
description: >
  Use ONLY when a task involves or might involve modifying files in core/ or releases/.
  Prevents accidental CORE FREEZE violations by blocking any edit, import, or reference
  to core/ or releases/ directories.
---

# Core Freeze Guard

## When to trigger
- The user mentions modifying core/ or releases/
- A task involves importing from core/ or releases/
- Any file path contains `core/` or `releases/`
- The user asks about adding features to the runtime, memory, or cognitive layers

## Rules
1. **BLOCK** any edit attempt on files under `core/` or `releases/`
2. **BLOCK** any import statement targeting `core/` or `releases/`
3. Redirect all work to `emo-desktop/lib/`, `emo-desktop/ui/`, `emo-desktop/tests/`
4. If the user insists, output a STOP-REPORT and refuse:

```
STOP-REPORT | CORE-FREEZE-GUARD | CORE_VIOLATION | [file/reason] | BLOCKED + AUDIT
```

## Allowed directories
- `emo-desktop/lib/**`
- `emo-desktop/ui/**`
- `emo-desktop/tests/**`
- `emo-desktop/docs/**`
- `emo-desktop/config/**`
- `emo-desktop/scripts/**`
- `artifacts/**`
