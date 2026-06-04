#!/bin/bash
# EMO AI Documentation — PDF Export Script
# Generates EMO-Docs-v1.0.pdf from all 5 guides
# Requires: pandoc, weasyprint or wkhtmltopdf

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DOCS_DIR="$(dirname "$SCRIPT_DIR")/guides"
OUTPUT_DIR="$(dirname "$SCRIPT_DIR")/portal"
VERSION="1.0.0"
OUTPUT_FILE="${OUTPUT_DIR}/EMO-Docs-v${VERSION}.pdf"

if [ ! -d "$DOCS_DIR" ]; then
  echo "ERROR: Guides directory not found at $DOCS_DIR"
  exit 1
fi

GUIDES=(
  "user-guide.md"
  "admin-guide.md"
  "security-guide.md"
  "api-guide.md"
  "deployment-guide.md"
)

MISSING=0
for guide in "${GUIDES[@]}"; do
  if [ ! -f "${DOCS_DIR}/${guide}" ]; then
    echo "WARNING: ${guide} not found — will be skipped"
    MISSING=$((MISSING + 1))
  fi
done

echo "================================================"
echo " EMO AI Documentation PDF Generator v${VERSION}"
echo "================================================"
echo "Guides directory: ${DOCS_DIR}"
echo "Output: ${OUTPUT_FILE}"
echo ""

TITLE_FILE=$(mktemp)
cat > "$TITLE_FILE" << EOF
---
title: "EMO AI Documentation"
subtitle: "Version ${VERSION} — Production Release"
date: "$(date +%Y-%m-%d)"
toc: true
toc-depth: 3
---
EOF

if command -v pandoc &> /dev/null; then
  echo "Building PDF with pandoc..."

  pandoc "$TITLE_FILE" \
    "${DOCS_DIR}/user-guide.md" \
    "${DOCS_DIR}/admin-guide.md" \
    "${DOCS_DIR}/security-guide.md" \
    "${DOCS_DIR}/api-guide.md" \
    "${DOCS_DIR}/deployment-guide.md" \
    -o "$OUTPUT_FILE" \
    --pdf-engine=weasyprint \
    --metadata title="EMO AI Documentation v${VERSION}" \
    --from markdown+smart \
    --highlight-style=tango 2>/dev/null || {

    echo "Trying wkhtmltopdf fallback..."
    pandoc "$TITLE_FILE" \
      "${DOCS_DIR}/user-guide.md" \
      "${DOCS_DIR}/admin-guide.md" \
      "${DOCS_DIR}/security-guide.md" \
      "${DOCS_DIR}/api-guide.md" \
      "${DOCS_DIR}/deployment-guide.md" \
      -o "$OUTPUT_FILE" \
      --pdf-engine=wkhtmltopdf \
      --metadata title="EMO AI Documentation v${VERSION}" \
      --from markdown+smart
  }

  echo ""
  if [ -f "$OUTPUT_FILE" ]; then
    SIZE=$(du -h "$OUTPUT_FILE" | cut -f1)
    echo "SUCCESS: ${OUTPUT_FILE} (${SIZE})"
  else
    echo "WARNING: PDF generation may have failed — check pandoc installation"
    echo "  Install: brew install pandoc weasyprint"
    echo "  Or:      pip install weasyprint"
    exit 1
  fi
else
  echo "WARNING: pandoc not found. Install with:"
  echo "  brew install pandoc weasyprint"
  echo ""
  echo "Creating placeholder metadata file..."
  cat > "${OUTPUT_DIR}/EMO-Docs-v${VERSION}.meta.json" << EOFEOF
{
  "title": "EMO AI Documentation v${VERSION}",
  "guides": ["user-guide", "admin-guide", "security-guide", "api-guide", "deployment-guide"],
  "generatedAt": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "status": "PDF generation requires pandoc"
}
EOFEOF
  echo "Metadata written to: ${OUTPUT_DIR}/EMO-Docs-v${VERSION}.meta.json"
fi

rm -f "$TITLE_FILE"
echo "Done."
