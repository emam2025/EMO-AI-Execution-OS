#!/bin/bash
# Phase J2 — Enterprise Release Archive Creation
# Ref: EXEC-DIRECTIVE-FINAL-ARCHIVE-001 §Task-2
#
# Creates the compressed enterprise release archive,
# excluding .git, __pycache__, *.pyc, and build artifacts.

set -euo pipefail

ARCHIVE_NAME="emo-ai-v4.11.0-enterprise-ready-archive.tar.gz"

echo "==> Creating enterprise release archive: ${ARCHIVE_NAME}"

tar --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='*.pyo' \
    --exclude='venv' \
    --exclude='.env' \
    --exclude='.emo_settings.json' \
    -czf "${ARCHIVE_NAME}" \
    artifacts/release/ \
    artifacts/enterprise/ \
    artifacts/pilot/ \
    artifacts/k5/ \
    artifacts/p1/ \
    docs/ \
    DEVELOPER.md \
    CHANGELOG.md \
    "EMO-AI-PROJECT ROADMAP.md" \
    ENTERPRISE_RELEASE_SUMMARY.md

echo "==> Archive created successfully."
ls -lh "${ARCHIVE_NAME}"

# Compute SHA-256
ARCHIVE_HASH=$(shasum -a 256 "${ARCHIVE_NAME}" | cut -d' ' -f1)
ARCHIVE_SIZE=$(stat -f%z "${ARCHIVE_NAME}")

echo "==> Archive SHA-256: ${ARCHIVE_HASH}"
echo "==> Archive size: ${ARCHIVE_SIZE} bytes"

# Write metadata
cat > artifacts/release/ARCHIVE_METADATA.json <<JSONEOF
{
  "archive": "${ARCHIVE_NAME}",
  "sha256": "${ARCHIVE_HASH}",
  "size_bytes": ${ARCHIVE_SIZE},
  "created_at_ns": $(date +%s%N),
  "version": "4.11.0-enterprise-ready",
  "contents": [
    "artifacts/release/",
    "artifacts/enterprise/",
    "artifacts/pilot/",
    "artifacts/k5/",
    "artifacts/p1/",
    "docs/",
    "DEVELOPER.md",
    "CHANGELOG.md",
    "EMO-AI-PROJECT ROADMAP.md",
    "ENTERPRISE_RELEASE_SUMMARY.md"
  ]
}
JSONEOF

echo "==> Metadata written to artifacts/release/ARCHIVE_METADATA.json"
