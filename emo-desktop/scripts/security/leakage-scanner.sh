#!/usr/bin/env bash
#
# leakage-scanner.sh — Artifact & Secret Leak Detection
#
# Scans build artifacts, source, and configuration for:
#   - API key patterns (sk-, ghp_, Bearer, etc.)
#   - Internal paths (/core/, /releases/)
#   - Architectural terms in user-facing output
#   - Exposed credentials in config files
#
# Generates leakage-report.json and exits with code 1 if
# CRITICAL or HIGH findings are detected.
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
REPORT="${ROOT_DIR}/leakage-report.json"
FAILED=0
TIMESTAMP="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

echo "=== Leakage Scanner ==="
echo "Root: ${ROOT_DIR}"
echo ""

# Directories to scan
SCAN_DIRS=(
  "${ROOT_DIR}/dist"
  "${ROOT_DIR}/installers"
  "${ROOT_DIR}/src-tauri/target"
  "${ROOT_DIR}/lib"
  "${ROOT_DIR}/ui/src"
  "${ROOT_DIR}/tests"
  "${ROOT_DIR}/scripts"
  "${ROOT_DIR}/docs"
)

# Directories to exclude
EXCLUDE_PATTERNS=(
  "node_modules/"
  ".git/"
  "__pycache__/"
  "*.lock"
  "*.png"
  "*.ico"
  "*.icns"
)

build_exclude() {
  local result=""
  for p in "${EXCLUDE_PATTERNS[@]}"; do
    result="${result} --exclude-dir=${p}"
  done
  echo "${result}"
}

EXCLUDE_ARGS="$(build_exclude)"

# Patterns to detect
PATTERNS=(
  # API keys
  "sk-[a-zA-Z0-9]\{20,\}"
  "sk-ant-[a-zA-Z0-9]\{20,\}"
  "AIza[0-9A-Za-z_-]\{35,\}"
  "ghp_[a-zA-Z0-9]\{36,\}"
  "Bearer [a-zA-Z0-9_-]\{20,\}"

  # Internal paths
  "/core/"
  "/releases/"

  # Architectural terms in docs
  "DAG synthesis"
  "Substrate"
  "ExecutionEngine"
)

SEVERITY_MAP=(
  "CRITICAL"    # API key patterns
  "CRITICAL"    # Anthropic key
  "HIGH"        # Google key
  "HIGH"        # GitHub PAT
  "HIGH"        # Bearer token
  "HIGH"        # /core/ path
  "HIGH"        # /releases/ path
  "LOW"         # DAG synthesis
  "LOW"         # Substrate
  "LOW"         # ExecutionEngine
)

echo "{" > "${REPORT}"
echo "  \"scan_timestamp\": \"${TIMESTAMP}\"," >> "${REPORT}"
echo "  \"findings\": [" >> "${REPORT}"

FIRST=true
IDX=0

for DIR in "${SCAN_DIRS[@]}"; do
  if [ ! -d "${DIR}" ]; then
    continue
  fi

  for i in "${!PATTERNS[@]}"; do
    PATTERN="${PATTERNS[$i]}"
    SEVERITY="${SEVERITY_MAP[$i]}"

    while IFS=: read -r FILE LINE CONTENT; do
      if [ -z "${FILE}" ]; then
        continue
      fi

      # Skip if content matches an exclude pattern
      SHOULD_SKIP=false
      for EXCLUDE in "${EXCLUDE_PATTERNS[@]}"; do
        if echo "${FILE}" | grep -q "${EXCLUDE}"; then
          SHOULD_SKIP=true
          break
        fi
      done
      ${SHOULD_SKIP} && continue

      if [ "${FIRST}" = true ]; then
        FIRST=false
      else
        echo "," >> "${REPORT}"
      fi

      echo -n "    { \"file\": \"${FILE}\", \"line\": ${LINE}, \"severity\": \"${SEVERITY}\", \"pattern\": \"${PATTERN}\", \"snippet\": \"$(echo "${CONTENT}" | sed 's/"/\\"/g' | head -c 80)\" }" >> "${REPORT}"

      if [ "${SEVERITY}" = "CRITICAL" ] || [ "${SEVERITY}" = "HIGH" ]; then
        FAILED=1
        echo "  ❌ [${SEVERITY}] ${FILE}:${LINE} — matched ${PATTERN}"
      else
        echo "  ⚠️  [${SEVERITY}] ${FILE}:${LINE} — matched ${PATTERN}"
      fi
    done < <(rg -n "${PATTERN}" "${DIR}" 2>/dev/null || true)
  done
done

echo "" >> "${REPORT}"
echo "  ]," >> "${REPORT}"
echo "  \"summary\": {" >> "${REPORT}"
echo "    \"total_findings\": $(rg -c '' "${REPORT}" 2>/dev/null || echo 0)," >> "${REPORT}"
echo "    \"build_blocked\": ${FAILED}" >> "${REPORT}"
echo "  }" >> "${REPORT}"
echo "}" >> "${REPORT}"

echo ""
echo "=== Report: ${REPORT} ==="
if [ "${FAILED}" -eq 1 ]; then
  echo "❌ LEAKAGE DETECTED — CRITICAL or HIGH findings — build blocked"
  exit 1
else
  echo "✅ No critical or high findings — build allowed"
fi
