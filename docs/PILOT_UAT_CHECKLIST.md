# Pilot UAT Checklist — User Acceptance Testing

## Scenario: New User
Goal: Experience first-time installation and operation.

### 1. Installation
| # | Step | Expected Result | ✅ / ❌ |
|---|------|-----------------|--------|
| 1 | Download from GitHub Releases | Download completes in < 1 minute | |
| 2 | Open DMG/run EXE/run AppImage | Application opens without errors | |
| 3 | Drag to Applications (macOS) | App appears in Launchpad | |
| 4 | System security: no warnings | Or "Unidentified Developer" message with Open Anyway option | |
| 5 | Uninstall | Application fully removed | |

### 2. First Run
| # | Step | Expected Result | ✅ / ❌ |
|---|------|-----------------|--------|
| 1 | Open app after installation | First Run Wizard appears | |
| 2 | Select Welcome → Next | Next step appears | |
| 3 | Choose AI mode (Local/Hybrid/Cloud) | Mode is saved | |
| 4 | Add API key (Settings → Models) | Keychain stores the key | |
| 5 | Create project | Project appears in Projects | |
| 6 | Launch → Dashboard appears | Correct Dashboard preview | |

### 3. Agent Execution
| # | Step | Expected Result | ✅ / ❌ |
|---|------|-----------------|--------|
| 1 | Navigate to Agents | Agent list appears | |
| 2 | Create new agent | Agent is created | |
| 3 | Enter request (e.g., "Say Hello") | Agent responds | |
| 4 | View result | Result appears in UI | |
| 5 | Test streaming | Text appears progressively | |

### 4. Monitoring & Management
| # | Step | Expected Result | ✅ / ❌ |
|---|------|-----------------|--------|
| 1 | Dashboard → System status | System Status = Connected | |
| 2 | Monitor → Performance | Charts appear | |
| 3 | Projects → Create task | Task is created | |
| 4 | Settings → Keychain | Keys appear masked | |

### 5. UAT Metrics
| Metric | Target | Result |
|--------|--------|--------|
| Installation time | < 2 minutes | |
| First run time | < 5 minutes | |
| Agent creation success | > 90% | |
| Task execution success | > 90% | |
| Crash rate | < 1% | |

### 6. Feedback Survey (Optional)
1. Did you encounter any difficulties during installation?
2. Did you find the First Run Wizard helpful?
3. Did the application respond satisfactorily?
4. Do you have suggestions for improvement?
