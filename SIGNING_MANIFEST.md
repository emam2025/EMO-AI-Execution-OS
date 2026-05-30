# Signing Manifest — EMO AI Execution OS v4.15.0-delivery-ready

## Component Hashes (archive contents)

| File | SHA-256 |
|---|---|
| `artifacts/final_prep/FINAL_DELIVERY_CERTIFICATE.json` | `ea21572899660135cd220549342a8d348c33c6e970cc67c2cc7ba7576cebb98d` |
| `artifacts/implementation/phase_g/01_implementation_report.md` | `75f0e4feb2b782f466c98ff7afc4e6569563d3d9c3db6980c42578f15b3c2407` |
| `artifacts/validation/memory/MEMORY_OPERATIONAL_CERTIFICATE.json` | `998d6c138378eadd4b57a06894d5d14111228229a094c88ae7bdc8a90aaa671d` |
| `artifacts/security/dependency_audit.json` | `1436ee7261c5da5c79338995135801d1baf7de505262b64e97fa64bec140c898` |
| `artifacts/debt/DEBT_RESOLUTION_PLAN.md` | `f442789ec5a1b2049640aac7ef3ee86a8fc9bc535d56a8f90549d6b1db5e163a` |
| `CHANGELOG.md` | `996e809d2a42fb5dee8661e6bc64b83887c64f1994a9b9347711c4ac0014948e` |
| `DEVELOPER.md` | `85b14a9ed7c3640f9149db3c106208f75d67ff6ad52bca36621ea0cec8645b8d` |
| `ROADMAP.md` | `7b7c0cfb518c1faf3c1f4d17fcbb18f33c0ef753f4031370a286d1116ff72f99` |
| `FINAL_RELEASE_REPORT.md` | `5a126223e4d0d54c86a595f6b9f65324704acfe7ebd8f530d9cf7196c65557cb` |

## Archive Signature

The final archive SHA-256 is published externally. To verify component integrity:

```bash
# Extract
tar xzf emo-ai-v4.15.0-release-archive.tar.gz

# Verify individual files
shasum -a 256 -c SIGNING_MANIFEST.md  # (trust the extracted manifest)
```

## Certifying Authority

- **Directive**: EXEC-DIRECTIVE-FINAL-RELEASE-001
- **Timestamp**: 2026-05-29T06:53:00Z
- **Tag**: `v4.15.0-delivery-ready`
- **Status**: 🟢 **SIGNED — DELIVERY READY**
