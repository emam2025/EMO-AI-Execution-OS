# Code Signing Guide — EMO AI Desktop

## Prerequisites

- **Apple Developer Program** ($99/year) for macOS signing + notarization
- **Microsoft Partner Center** (or self-signed cert) for Windows Authenticode
- **GPG key** for Linux AppImage signing (recommended)

---

## 1. macOS Signing + Notarization

### 1.1 Get Certificates

```bash
# Request a "Developer ID Application" certificate from:
# Apple Developer → Certificates → (+) → Developer ID Application
# Download and double-click to install in Keychain
# Verify:
security find-identity -v -p basic | grep "Developer ID Application"
```

### 1.2 Configure tauri.conf.json

```json
{
  "bundle": {
    "macOS": {
      "signingIdentity": "Developer ID Application: Your Name (TEAMID)",
      "entitlements": "entitlements.plist",
      "minimumSystemVersion": "12.0"
    }
  },
  "plugins": {
    "updater": {
      "pubkey": "<see .pub file>"
    }
  }
}
```

### 1.3 Create entitlements.plist

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>com.apple.security.cs.allow-jit</key>
    <true/>
    <key>com.apple.security.network.client</key>
    <true/>
    <key>com.apple.security.network.server</key>
    <true/>
</dict>
</plist>
```

### 1.4 Notarization

```bash
# After build, notarize:
xcrun notarytool submit \
  --apple-id "your@email.com" \
  --team-id "TEAMID" \
  --password "@keychain:AC_PASSWORD" \
  --wait \
  "target/release/bundle/dmg/EMO AI.dmg"

# Staple ticket:
xcrun stapler staple "target/release/bundle/dmg/EMO AI.dmg"
```

### 1.5 CI Setup

Add these secrets to GitHub:
- `APPLE_CERTIFICATE`: Base64-encoded `.p12` certificate
- `APPLE_CERTIFICATE_PASSWORD`: Password for the `.p12`
- `APPLE_ID`: Apple Developer email
- `APPLE_ID_PASSWORD`: App-specific password (generate at appleid.apple.com)
- `APPLE_TEAM_ID`: Your Team ID

Then add to `desktop-build.yml`:

```yaml
- name: Import certificate
  if: matrix.os == 'macos-latest'
  run: |
    echo "${{ secrets.APPLE_CERTIFICATE }}" | base64 -d > /tmp/cert.p12
    security create-keychain -p temp /tmp/build.keychain
    security default-keychain -s /tmp/build.keychain
    security unlock-keychain -p temp /tmp/build.keychain
    security import /tmp/cert.p12 -k /tmp/build.keychain \
      -P "${{ secrets.APPLE_CERTIFICATE_PASSWORD }}" -T /usr/bin/codesign
    security set-key-partition-list -S apple-tool:,apple:,codesign: \
      -s -k temp /tmp/build.keychain
```

---

## 2. Windows Signing

### 2.1 Get Certificate

```bash
# Option A: Buy from DigiCert/Sectigo/GoDaddy
# Option B: Let Tauri build without signing (unsigned EXE)
```

### 2.2 Configure

The Wix/NSIS config in `tauri.conf.json` already exists. Add:

```json
{
  "bundle": {
    "windows": {
      "wix": {
        "digestAlgorithm": "sha256",
        "languages": ["en-US"]
      },
      "nsis": {
        "installMode": "currentUser"
      }
    }
  }
}
```

### 2.3 CI Setup

Add secrets:
- `WINDOWS_CERTIFICATE`: Base64-encoded `.pfx`
- `WINDOWS_CERTIFICATE_PASSWORD`

---

## 3. Linux Signing

Linux AppImages do not require mandatory signing. For AppImageUpdate:

```bash
# Sign with GPG
gpg --detach-sign --armor EMO_AI-*.AppImage
# Verify:
gpg --verify EMO_AI-*.AppImage.asc
```

---

## 4. Verifying Signing

```bash
# macOS
codesign -dvvv "EMO AI.app"
spctl --assess --type execute "EMO AI.app"

# Windows
signtool verify /pa /v "EMO AI Setup.exe"

# Linux
gpg --verify "EMO AI.AppImage.asc"
```

---

## 5. Current Config Status

| Platform | Signing Identity | Status | Action Needed |
|----------|-----------------|--------|--------------|
| macOS | `null` | ❌ Not configured | Buy Apple Developer ($99), fill signingIdentity |
| Windows | Built-in Wix/NSIS | ⚠️ Partial | No certificate configured |
| Linux | GPG opt-in | ✅ Optional | Configure if auto-update needed |

*Last updated: 2026-06-26*
