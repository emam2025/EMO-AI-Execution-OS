# EMO AI — User Guide

> Your personal AI workspace. Install it. Set it up. Run your agents.

---

## Getting Started

### Download & Install

**macOS**
1. Download `EMO.dmg` from the [releases page](https://releases.emo-ai.dev).
2. Double-click the `.dmg` file.
3. Drag `EMO.app` into your `Applications` folder.
4. Open `EMO.app` from Applications (right-click → Open on first launch).

**Windows**
1. Download `EMO-Setup.exe` from the [releases page](https://releases.emo-ai.dev).
2. Double-click the installer.
3. Follow the setup wizard. A desktop shortcut will be created automatically.
4. Launch EMO AI from the Start menu or desktop shortcut.

**Linux**
1. Download `EMO.AppImage` from the [releases page](https://releases.emo-ai.dev).
2. Right-click the file → Properties → Permissions → Allow executing as program.
3. Double-click to launch.

> **Screenshot:** `screenshots/installer-mac.png` — EMO.dmg with drag-to-Applications arrow
> **Screenshot:** `screenshots/installer-win.png` — EMO-Setup.exe welcome screen
> **Screenshot:** `screenshots/installer-linux.png` — EMO.AppImage with permissions dialog

---

## First Run — Setting Up Your API Key

When you launch EMO AI for the first time, the **First Run Wizard** will guide you through connecting your AI providers.

1. **Welcome Screen** — Click "Get Started".
2. **Choose a Provider** — Select the AI service you use (e.g., OpenAI, Anthropic, Gemini).
3. **Enter Your API Key** — Paste your key into the secure field.
   - Your key is stored in your computer's **keychain** (the same secure place where your passwords live).
   - It is never saved to a file, never visible in settings, and never sent anywhere without your permission.
4. **Confirm** — EMO AI will test the connection. If it works, you're all set.
5. **Done** — The wizard closes and you're ready to create your first project.

> **Screenshot:** `screenshots/wizard-welcome.png` — Welcome screen with "Get Started" button
> **Screenshot:** `screenshots/wizard-api-key.png` — Secure API key entry field with keychain icon
> **Screenshot:** `screenshots/wizard-success.png` — Confirmation screen after successful test

**Changing or Adding Keys Later:**
- Open **Settings** → **Providers**.
- Click the pencil icon next to a provider to update its key.
- Your existing key is never shown — you'll type a new one to replace it.

---

## Creating Projects

A **Project** is a workspace where you organize your work. Each project has its own memory, team of agents, and knowledge files.

1. Click **+ New Project** in the sidebar.
2. Give your project a name (e.g., "Q2 Marketing Research").
3. (Optional) Add a short description.
4. Click **Create**.

**Inside a Project:**
- **Memory** — Information the project has learned. You can review or clear it.
- **Agents** — The smart workers assigned to this project (see below).
- **Knowledge Base** — Files, notes, and references your agents can use.

> **Screenshot:** `screenshots/project-create.png` — New Project dialog
> **Screenshot:** `screenshots/project-overview.png` — Project dashboard showing Memory, Agents, Knowledge Base

---

## Running Agents

An **Agent** is a smart worker you assign to a task. You give it instructions, it works, and you get results.

1. Open a project.
2. Click **+ New Agent**.
3. Give your agent a name and describe what it should do.
   - Example: "Research competitor pricing and summarize findings."
4. (Optional) Connect memory or knowledge files the agent should reference.
5. Click **Run**.

**While the agent is working:**
- You'll see its progress in real time.
- It shows what it's reading, thinking, and writing.

**When it's done:**
- The result appears in the project feed.
- You can copy, export, or ask follow-up questions.

> **Screenshot:** `screenshots/agent-running.png` — Agent progress view with live status
> **Screenshot:** `screenshots/agent-result.png` — Completed result with export buttons

---

## Troubleshooting

| Problem | Solution |
|---|---|
| "Invalid API Key" error | Check you copied the full key. Keys usually start with `sk-` or similar prefixes. Generate a new key from your provider's dashboard. |
| App won't open (macOS) | Right-click → Open. On first launch, macOS may block unsigned apps. |
| App won't open (Linux) | Make sure the `.AppImage` file has execute permission: right-click → Properties → Permissions → Allow executing. |
| No internet connection | EMO AI needs an internet connection to run agents. Check your network. |
| Update available notification | Updates are verified automatically. Click "Update" to install the latest version. |
| Forgot which providers I set up | Go to **Settings** → **Providers** to see all connected services. |

> **Need more help?** Visit our [support page](https://support.emo-ai.dev) or email support@emo-ai.dev.

---

## Quick Reference

| Action | How |
|---|---|
| Install | Download from releases.emo-ai.dev |
| Add API Key | First Run Wizard or Settings → Providers |
| Create Project | Sidebar → + New Project |
| Run Agent | Open project → + New Agent → Run |
| Update App | Settings → Updates → Update |
| Clear Memory | Project → Memory → Clear |

---

