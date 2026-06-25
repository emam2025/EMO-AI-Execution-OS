# EMO AI — User Guide
## User Guide v1.0

### What is EMO AI?
EMO AI is your smart assistant for task management and automation. You can create agents that work on multiple tasks using different AI models.

### Quick Start
1. **Install the application** → Open EMO AI
2. **Choose operation mode** → Local / Hybrid / Cloud
3. **Add API key** → Settings → Models → Keychain
4. **Create a project** → and create your first agent
5. **Run a task** → Write your request

### Main Screens

| Screen | Function |
|---|---|
| **Dashboard** | Overview: system status, active agents, recent tasks |
| **Agents** | Create and manage AI agents |
| **Projects** | Manage projects and tasks |
| **Models** | Connect AI models (OpenAI, OpenRouter, Groq, Gemini, Ollama) |
| **Knowledge** | Knowledge and history repository |
| **Monitor** | Performance and system monitoring |
| **Security** | Security and permissions settings |
| **Settings** | Application and key settings |

### Key Security
- All API keys are stored in the **System Keychain** (macOS Keychain / Windows Credential Manager / Linux Secret Service)
- Keys are not stored in files or in Git
- Keys are injected into memory only during runtime

### Troubleshooting
| Problem | Solution |
|---|---|
| Application does not connect | Make sure the backend service is running (Settings → Connection) |
| Model does not respond | Make sure a valid API key is added in Settings → Models |
| Slow response | Use local mode (Ollama) or improve internet speed |
