# EMO AI — Installation Guide
## Installation Guide v1.0

### System Requirements
| Platform | Requirements |
|---|---|
| **macOS** | macOS 13+ (Ventura) |
| **Windows** | Windows 10+ |
| **Linux** | Ubuntu 22.04+ / Fedora 38+ |

### Installation

#### macOS
1. Download the `EMO-AI.dmg` file
2. Open DMG → Drag `EMO AI` to the Applications folder
3. Open the application from Launchpad
4. If an "Unidentified Developer" warning appears: go to System Settings → Privacy & Security → Open Anyway

#### Windows
1. Download the `EMO-AI-Setup.exe` file
2. Run the installer → Follow the instructions
3. Open EMO AI from the Start Menu

#### Linux
1. Download `EMO-AI.AppImage`
2. `chmod +x EMO-AI.AppImage`
3. `./EMO-AI.AppImage`
   Or: `sudo dpkg -i emo-ai.deb` (if you are using .deb)

### Initial Setup
1. On first run, the **First Run Wizard** will appear
2. Follow the steps:
   - **Welcome** → Start
   - **Choose AI Mode** → Local / Hybrid / Cloud
   - **Connect Model** → Add API key (OpenRouter, OpenAI, etc.) via Keychain
   - **Create Project** → Name your first project
   - **Launch** → Start!
3. Congratulations! EMO AI is ready to use 🎉

### Updates
- The application checks for updates automatically on startup
- You can enable automatic updates from Settings → Updates

### Uninstallation
- **macOS**: Drag `EMO AI` from the Applications folder to Trash
- **Windows**: Control Panel → Programs → Uninstall
- **Linux**: `sudo apt remove emo-ai` or delete the AppImage
