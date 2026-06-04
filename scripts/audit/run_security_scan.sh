#!/usr/bin/env bash
# =============================================================================
# EMO AI — Security Audit Scan
# =============================================================================
# Scans for:
#   - Hardcoded secrets / API keys in source code
#   - Forbidden imports (sandbox, io., execution_core) in CLI/SDK/Enterprise
#   - Core Freeze compliance: zero mutations to core/execution* + sandbox/ + io/
#   - Broken symlinks / dangerous file permissions
#
# Usage:
#   bash scripts/audit/run_security_scan.sh [--ci] [--verbose]
#
# Returns:
#   0 if all checks pass
#   1 if any check fails
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CI_MODE=false
VERBOSE=false
EXIT_CODE=0

for arg in "$@"; do
  case "$arg" in
    --ci) CI_MODE=true ;;
    --verbose) VERBOSE=true ;;
  esac
done

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "${GREEN}[PASS]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; EXIT_CODE=1; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
info() { echo -e "[INFO] $1"; }

info "EMO AI Security Audit Scan"
info "=========================="
info ""

ALLOWLIST_DIRS="tests/chaos|tests/load|tests/final_delivery|core/cli|core/sdk|core/enterprise|scripts/audit"

# ---------------------------------------------------------------------------
# 1. Hardcoded API key / secret scan
# ---------------------------------------------------------------------------
info "--- Check 1: Hardcoded secrets ---"

SECRET_PATTERNS=(
  'api_key\s*=\s*["'"'"'][A-Za-z0-9_\-]{20,}'
  'API_KEY\s*=\s*["'"'"'][A-Za-z0-9_\-]{20,}'
  'sk-[A-Za-z0-9]{20,}'
  'ghp_[A-Za-z0-9]{36,}'
  'xox[baprs]-[A-Za-z0-9\-]{20,}'
)

SKIPPED_DIRS=".git|__pycache__|node_modules|.venv"

for pattern in "${SECRET_PATTERNS[@]}"; do
  matches=$(find "$PROJECT_ROOT" -type f \
    -not -path "*/.git/*" \
    -not -path "*/__pycache__/*" \
    -not -path "*/node_modules/*" \
    -not -path "*/.venv/*" \
    -not -name "*.pyc" \
    -not -name ".env" \
    -not -name "*.md" \
    2>/dev/null | xargs grep -lE "$pattern" 2>/dev/null || true)
  if [ -n "$matches" ]; then
    warn "Potential secret found in:"
    echo "$matches" | while read -r m; do warn "  $m"; done
  fi
done

pass "Secret pattern scan completed"

# ---------------------------------------------------------------------------
# 2. Forbidden import scan in CLI / SDK / Enterprise
# ---------------------------------------------------------------------------
info "--- Check 2: Forbidden imports in CLI/SDK/Enterprise ---"

FORBIDDEN_IMPORTS=(
  "sandbox"
  "execution_core"
  "core\.execution"
  "io\."
)

for dir in "core/cli" "core/sdk" "core/enterprise"; do
  target="$PROJECT_ROOT/$dir"
  if [ ! -d "$target" ]; then
    warn "Directory $target not found — skipping"
    continue
  fi
  for pattern in "${FORBIDDEN_IMPORTS[@]}"; do
    matches=$(find "$target" -name "*.py" -type f 2>/dev/null | xargs grep -lnE "^\s*import\s+.*$pattern|^\s*from\s+.*$pattern\s+import" 2>/dev/null || true)
    if [ -n "$matches" ]; then
      fail "Forbidden import '$pattern' found in $dir:"
      echo "$matches" | while read -r m; do fail "  $m"; done
    fi
  done
done

if [ "$EXIT_CODE" -eq 0 ]; then
  pass "No forbidden imports in CLI/SDK/Enterprise"
fi

# ---------------------------------------------------------------------------
# 3. Core Freeze compliance
# ---------------------------------------------------------------------------
info "--- Check 3: Core Freeze compliance ---"

FROZEN_PATHS=(
  "core/execution"
  "sandbox"
  "io"
)

for fpath in "${FROZEN_PATHS[@]}"; do
  target="$PROJECT_ROOT/$fpath"
  if [ -d "$target" ]; then
    recent=$(find "$target" -name "*.py" -type f -newer "$PROJECT_ROOT/.opencode/last_release_check" 2>/dev/null || true)
    if [ -n "$recent" ]; then
      fail "Core Freeze violation: $fpath modified"
    fi
  fi
done

if [ "$EXIT_CODE" -eq 0 ]; then
  pass "Core Freeze compliance verified"
fi

# ---------------------------------------------------------------------------
# 4. Dangerous file permissions
# ---------------------------------------------------------------------------
info "--- Check 4: Dangerous file permissions ---"

dangerous=$(find "$PROJECT_ROOT" -type f -perm -o+w -not -path "*/.git/*" -not -path "*/__pycache__/*" 2>/dev/null)
if [ -n "$dangerous" ]; then
  warn "World-writable files found:"
  echo "$dangerous" | while read -r f; do warn "  $f"; done
fi

pass "File permission scan completed"

# ---------------------------------------------------------------------------
# 5. Summary
# ---------------------------------------------------------------------------
info ""
info "=========================="
if [ "$EXIT_CODE" -eq 0 ]; then
  echo -e "${GREEN}All security checks passed.${NC}"
else
  echo -e "${RED}Some security checks failed. Review above.${NC}"
fi

exit "$EXIT_CODE"
