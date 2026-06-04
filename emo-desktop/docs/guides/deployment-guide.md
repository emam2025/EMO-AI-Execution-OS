# EMO AI — Deployment Guide

> For IT teams deploying EMO AI across their organisation.

---

## Silent Installation

Silent (unattended) installation lets you deploy EMO AI without user interaction — ideal for MDM, Group Policy, or remote deployment.

### macOS — Silent DMG Install

```bash
# Mount the DMG
hdiutil attach /path/to/EMO.dmg

# Copy to Applications
cp -R "/Volumes/EMO AI/EMO.app" /Applications/

# Unmount
hdiutil detach "/Volumes/EMO AI"

# Notarization check (if applicable)
spctl --assess --verbose /Applications/EMO.app
```

**MDM Deployment:** Use your MDM tool (Jamf, Kandji, Fleet) to push `EMO.app` to `/Applications/` with a configuration profile that approves the app's gatekeeper bypass on first launch.

### Windows — Silent NSIS Install

```powershell
# Basic silent install
EMO-Setup.exe /S

# Install with custom path
EMO-Setup.exe /S /D=C:\Program Files\EMO AI

# Verify installation
Get-ItemProperty "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\EMO AI"
```

**Group Policy Deployment:**
1. Place `EMO-Setup.exe` on a network share.
2. Create a GPO with a Computer Configuration → Software Installation policy.
3. Assign the package to target OUs.

### Linux — Silent AppImage Deployment

```bash
# Copy to user's local bin
cp EMO.AppImage ~/.local/bin/
chmod +x ~/.local/bin/EMO.AppImage

# System-wide installation (requires sudo)
sudo cp EMO.AppImage /usr/local/bin/
sudo chmod +x /usr/local/bin/EMO.AppImage

# Verify
~/.local/bin/EMO.AppImage --version
```

**Enterprise Deployment:**
- Use configuration management tools (Ansible, Puppet, Chef) to distribute the AppImage.
- Example Ansible task:
```yaml
- name: Install EMO AI
  copy:
    src: EMO.AppImage
    dest: /usr/local/bin/EMO.AppImage
    mode: '0755'
```

---

## Configuration Management

### Shared Team Configuration

Distribute default settings to all users by placing a configuration file:

**macOS:** `~/Library/Application Support/emo-desktop/config.json`
**Windows:** `%APPDATA%\emo-desktop\config.json`
**Linux:** `~/.config/emo-desktop/config.json`

Example configuration:

```json
{
  "default_provider": "openai",
  "theme": "light",
  "update_channel": "stable",
  "memory_limit_mb": 512,
  "auto_update": true
}
```

### Pre-Configured Providers

To pre-populate provider settings (without keys — users must enter their own keys on first run):

```json
{
  "providers": [
    {
      "id": "openai",
      "enabled": true,
      "label": "Company OpenAI Account"
    }
  ]
}
```

---

## Update Channels

EMO AI supports two update channels:

| Channel | Frequency | Stability | Use Case |
|---|---|---|---|
| **Stable** | Monthly | Fully tested | Production deployment |
| **Beta** | Weekly | Feature preview | Test environments |

### Switching Channels

1. Open **Settings** → **Updates**.
2. Click **Change Channel**.
3. Select **Stable** or **Beta**.
4. The app will check for available updates on the new channel.

### Enterprise Pin to Version

To prevent automatic updates and pin a specific version:

```json
{
  "auto_update": false,
  "pinned_version": "0.1.0"
}
```

When pinned, update notifications are suppressed. To unpin, remove the `pinned_version` field.

---

## Rollback Procedure

If an update causes issues, follow these steps:

### Automatic Rollback

1. Open the app → **Settings** → **Updates** → **Version History**.
2. Click **Rollback** next to the previous working version.
3. Confirm. The app will reinstall the previous version and restart.

### Manual Rollback

If the app won't launch after an update:

**macOS:**
```bash
# Remove current version
rm -rf /Applications/EMO.app

# Reinstall previous version from backup
cp -R /path/to/backup/EMO.app /Applications/
```

**Windows:**
```powershell
# Uninstall current version
EMO-Setup.exe /S /uninstall

# Install previous version
.\EMO-Setup-v0.1.0.exe /S
```

**Linux:**
```bash
# Replace with previous AppImage
cp ~/backups/EMO-AppImage-v0.1.0 ~/.local/bin/EMO.AppImage
chmod +x ~/.local/bin/EMO.AppImage
```

### Backup Recommendations

- Keep the last 2 installer versions in a network share before deploying updates.
- Verify updates on a test machine before rolling to production.
- Maintain a deployment log with version, date, and any issues encountered.

---

## System Requirements

| Platform | Minimum | Recommended |
|---|---|---|
| **macOS** | 12.0 Monterey, Intel or Apple Silicon | 14.0 Sonoma, Apple Silicon, 8 GB RAM |
| **Windows** | Windows 10 64-bit, 4 GB RAM | Windows 11, 8 GB RAM |
| **Linux** | Ubuntu 20.04 / Fedora 36, 4 GB RAM | Ubuntu 24.04 / Fedora 40, 8 GB RAM |
| **Disk Space** | 500 MB | 1 GB (allows for knowledge files) |
| **Internet** | Broadband connection | Broadband connection |

---

## Deployment Checklist

- [ ] Silent install tested on all target platforms
- [ ] Team configuration file ready for distribution
- [ ] Update channel selected (Stable recommended)
- [ ] Rollback plan documented and tested
- [ ] Previous installer versions archived on network share
- [ ] Test deployment completed on pilot machines
- [ ] Helpdesk team briefed on installation steps
