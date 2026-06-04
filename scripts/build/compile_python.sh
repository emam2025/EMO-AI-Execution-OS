#!/usr/bin/env bash
set -euo pipefail
# ─────────────────────────────────────────────────────────────────
# compile_python.sh — Nuitka compilation for EMO AI Python backend
#
# Produces: dist/emo-desktop  (standalone binary)
# Requires: nuitka (pip install nuitka)
#
# Usage:
#   ./scripts/build/compile_python.sh          # production build
#   ./scripts/build/compile_python.sh --debug  # debug build
# ─────────────────────────────────────────────────────────────────

APP="main"
SRC="."
OUTDIR="dist/emo-desktop"
VENV_PYTHON="${VENV_PYTHON:-python3}"

echo "==> Compiling ${APP}.py with Nuitka ..."

# Clear previous build
rm -rf "${OUTDIR}" "${APP}.build"

ARGS=(
  --standalone
  --onefile
  --enable-plugin=no-qt
  --follow-import-to=core
  --follow-import-to=routers
  --follow-import-to=middleware
  --include-module=uvicorn
  --include-module=uvicorn.logging
  --include-module=uvicorn.loops
  --include-module=uvicorn.loops.auto
  --include-module=uvicorn.protocols
  --include-module=uvicorn.protocols.http.auto
  --include-module=uvicorn.lifespan.on
  --include-module=sse_starlette.sse
  --output-dir="${OUTDIR}"
  --output-filename=emo-runtime
  --remove-output
  --assume-yes-for-downloads
)

if [[ "${1:-}" != "--debug" ]]; then
  # Production: strip, LTO, no assert
  ARGS+=(--strip --lto --no-debug --no-asserts)
  echo "   Mode: PRODUCTION (strip + lto)"
else
  echo "   Mode: DEBUG"
fi

"${VENV_PYTHON}" -m nuitka "${ARGS[@]}" "${SRC}/${APP}.py"

echo "==> Done! Binary at: ${OUTDIR}/emo-runtime"
ls -lh "${OUTDIR}/emo-runtime"
