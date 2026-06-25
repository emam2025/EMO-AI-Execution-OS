# Pilot UAT Checklist — User Acceptance Testing

## Scenario: Completely New User
Goal: The user's first installation and operation experience.

### 1. Installation (Install)
| # | Step | Expected Result | ✅ / ❌ |
|---|--------|-----------------|--------|
| 1 | Download file from GitHub Releases | Download succeeds in < 1 minute | |
| 2 | Open DMG/Run EXE/Run AppImage | Application opens without errors | |
| 3 | Drag to Applications (macOS) | Application appears in Launchpad | |
| 4 | System security: no security warnings | Or "Unidentified Developer" message with Open Anyway option | |
| 5 | Uninstall | Application is deleted completely | |

### 2. First Run (First Run)
| # | Step | Expected Result | ✅ / ❌ |
|---|--------|-----------------|--------|
| 1 | Open application after installation | First Run Wizard appears | |
| 2 | Choose Welcome → Next | Next step appears | |
| 3 | Choose AI mode (Local/Hybrid/Cloud) | Mode is saved | |
| 4 | Add API key (Settings → Models) | Keychain stores the key | |
| 5 | Create project | Project appears in Projects | |
| 6 | Launch → Dashboard appears | Correct Dashboard preview | |

### 3. Run Agent
| # | Step | Expected Result | ✅ / ❌ |
|---|--------|-----------------|--------|
| 1 | Enter Agents | Agent list appears | |
| 2 | Create new agent (Agent) | Agent is created | |
| 3 | Enter request (example: "Say Hello") | Agent responds | |
| 4 | View result | Result appears in the UI | |
| 5 | Try streaming | Text appears continuously | |

### 4. Monitoring and Management
| # | Step | Expected Result | ✅ / ❌ |
|---|--------|-----------------|--------|
| 1 | Dashboard → System status | System Status = Connected | |
| 2 | Monitor → Performance | Charts appear | |
| 3 | Projects → Create task | Task is created | |
| 4 | Settings → Keychain | Keys appear hidden | |

### 5. Indicators (UAT Metrics)
| Indicator | Target | Result |
|--------|------|--------|
| Installation time | < 2 minutes | |
| First run time | < 5 minutes | |
| Agent creation success | > 90% | |
| Task execution success | > 90% | |
| Crash rate | < 1% | |

### 6. Survey (Optional)
1. Did you encounter any difficulty during installation?
2. Did you find the First Run Wizard useful?
3. Did the application respond at a satisfactory speed?
4. Do you have suggestions for the application?
