#!/usr/bin/env bash
# ────────────────────────────────────────────────────────────────
# binary_security_audit.sh
# فحص أمان الباينري — يتحقق من عدم وجود ملفات ممنوعة داخل DMG/EXE/AppImage
#
# Usage:
#   ./scripts/audit/binary_security_audit.sh path/to/EMO-AI.dmg
#   ./scripts/audit/binary_security_audit.sh path/to/EMO-AI-Setup.exe
#   ./scripts/audit/binary_security_audit.sh path/to/EMO-AI.AppImage
#
# الناتج:
#   artifacts/security/BINARY_SECURITY_CERTIFICATE.json
# ────────────────────────────────────────────────────────────────

BINARY="$1"
OUTPUT="artifacts/security/BINARY_SECURITY_CERTIFICATE.json"
HAS_ERROR=0

if [[ -z "$BINARY" ]]; then
  echo "Usage: $0 <path-to-binary>"
  echo "Example: $0 emo-desktop/src-tauri/target/release/bundle/dmg/EMO-AI.dmg"
  exit 1
fi

if [[ ! -f "$BINARY" ]]; then
  echo "ERROR: File not found: $BINARY"
  exit 1
fi

echo "========================================"
echo "BINARY SECURITY AUDIT"
echo "File: $BINARY"
echo "Size: $(du -sh "$BINARY" | cut -f1)"
echo "========================================"

RESULTS=()
TEMP_DIR=$(mktemp -d)
trap 'rm -rf "$TEMP_DIR"' EXIT

# Extract based on extension
case "$BINARY" in
  *.dmg)
    echo "Detected: macOS DMG"
    hdiutil attach "$BINARY" -mountpoint "$TEMP_DIR/mount" -quiet 2>/dev/null || {
      echo "WARN: Cannot mount DMG (may need macOS), trying 7z..."
      7z x -o"$TEMP_DIR/extract" "$BINARY" 2>/dev/null || true
    }
    if [[ -d "$TEMP_DIR/mount" ]]; then
      EXTRACTED="$TEMP_DIR/mount"
    else
      EXTRACTED="$TEMP_DIR/extract"
    fi
    ;;
  *.exe)
    echo "Detected: Windows EXE"
    7z x -o"$TEMP_DIR/extract" "$BINARY" 2>/dev/null
    EXTRACTED="$TEMP_DIR/extract"
    ;;
  *.AppImage)
    echo "Detected: Linux AppImage"
    "$BINARY" --appimage-extract 2>/dev/null
    EXTRACTED="squashfs-root"
    ;;
  *)
    echo "Unknown binary type. Supported: .dmg, .exe, .AppImage"
    exit 1
    ;;
esac

# ── Checks ─────────────────────────────────
echo ""
echo "--- Check 1: .env files ---"
FOUND=$(find "$EXTRACTED" -name ".env" 2>/dev/null)
if [[ -n "$FOUND" ]]; then
  echo "FAIL: .env found: $FOUND"
  RESULTS+=('{"check": "env_files", "status": "FAIL", "detail": ".env file present in binary"}')
  HAS_ERROR=1
else
  echo "PASS: No .env files"
  RESULTS+=('{"check": "env_files", "status": "PASS"}')
fi

echo ""
echo "--- Check 2: .py files ---"
FOUND=$(find "$EXTRACTED" -name "*.py" 2>/dev/null | head -5)
if [[ -n "$FOUND" ]]; then
  echo "FAIL: Python source found: $FOUND"
  RESULTS+=('{"check": "python_files", "status": "FAIL", "detail": "Python .py source files present in binary"}')
  HAS_ERROR=1
else
  echo "PASS: No .py files (should be Nuitka-compiled)"
  RESULTS+=('{"check": "python_files", "status": "PASS"}')
fi

echo ""
echo "--- Check 3: Source maps ---"
FOUND=$(find "$EXTRACTED" -name "*.map" 2>/dev/null | head -5)
if [[ -n "$FOUND" ]]; then
  echo "FAIL: Source maps found: $FOUND"
  RESULTS+=('{"check": "source_maps", "status": "FAIL", "detail": ".map files present in binary"}')
  HAS_ERROR=1
else
  echo "PASS: No source maps"
  RESULTS+=('{"check": "source_maps", "status": "PASS"}')
fi

echo ""
echo "--- Check 4: Debug logs ---"
FOUND=$(find "$EXTRACTED" -name "*.log" -o -name "debug.*" 2>/dev/null | head -5)
if [[ -n "$FOUND" ]]; then
  echo "WARN: Debug artifacts found: $FOUND"
  RESULTS+=('{"check": "debug_logs", "status": "WARN", "detail": "Debug files present"}')
else
  echo "PASS: No debug logs"
  RESULTS+=('{"check": "debug_logs", "status": "PASS"}')
fi

echo ""
echo "--- Check 5: Debug symbols (macOS) ---"
if [[ "$BINARY" =~ \.dmg$ ]]; then
  APP_PATH=$(find "$EXTRACTED" -name "*.app" -type d 2>/dev/null | head -1)
  if [[ -n "$APP_PATH" ]]; then
    SYMBOLS=$(dsymutil -s "$APP_PATH/Contents/MacOS/"* 2>/dev/null | wc -l)
    echo "   Debug symbols: $SYMBOLS lines"
    if [[ "$SYMBOLS" -gt 100 ]]; then
      echo "WARN: Extensive debug symbols found"
      RESULTS+=('{"check": "debug_symbols", "status": "WARN", "detail": "App contains debug symbols"}')
    else
      echo "PASS: Clean symbols"
      RESULTS+=('{"check": "debug_symbols", "status": "PASS"}')
    fi
  else
    echo "SKIP: No .app found in DMG"
    RESULTS+=('{"check": "debug_symbols", "status": "SKIP"}')
  fi
fi

echo ""
echo "--- Check 6: Credentials / secrets ---"
FOUND=$(find "$EXTRACTED" -name "*.pem" -o -name "*.key" -o -name "*credential*" -o -name "*secret*" 2>/dev/null | head -5)
if [[ -n "$FOUND" ]]; then
  echo "FAIL: Credential files found: $FOUND"
  RESULTS+=('{"check": "credentials", "status": "FAIL", "detail": "Sensitive files in binary"}')
  HAS_ERROR=1
else
  echo "PASS: No credential files"
  RESULTS+=('{"check": "credentials", "status": "PASS"}')
fi

# ── Generate JSON ──────────────────────────
echo ""
echo "========================================"

JSON_RESULTS="[${RESULTS[*]}]" | sed 's/} {/}, {/g'

# Build JSON manually to avoid sed issues
cat > "$OUTPUT" << JSONEOF
{
  "meta": {
    "certificate": "BINARY_SECURITY_CERTIFICATE",
    "project": "EMO AI Orchestrator",
    "binary": "$BINARY",
    "size": "$(du -sh "$BINARY" | cut -f1)",
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "branch": "release/v1-production-candidate"
  },
  "checks": [
JSONEOF

# Append results (already JSON fragments)
for ((i=0; i<${#RESULTS[@]}; i++)); do
  comma=""
  if [[ $i -lt $((${#RESULTS[@]}-1)) ]]; then
    comma=","
  fi
  echo "    ${RESULTS[$i]}$comma" >> "$OUTPUT"
done

cat >> "$OUTPUT" << JSONEOF
  ],
  "summary": {
    "all_checks_pass": $([ "$HAS_ERROR" -eq 0 ] && echo "true" || echo "false"),
    "overall": "$([ "$HAS_ERROR" -eq 0 ] && echo "PASS" || echo "FAIL")"
  }
}
JSONEOF

echo ""
echo "Certificate saved: $OUTPUT"
echo "OVERALL: $([ "$HAS_ERROR" -eq 0 ] && echo "PASS" || echo "FAIL")"

# Cleanup
if [[ -d "squashfs-root" ]]; then
  rm -rf squashfs-root
fi

exit $HAS_ERROR
