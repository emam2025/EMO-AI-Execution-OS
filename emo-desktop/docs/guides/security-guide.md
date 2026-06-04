# EMO AI — Security & Privacy Guide

> How your data stays safe, where your keys are stored, and what we never see.

---

## Key Storage — How EMO AI Protects Your API Keys

When you enter an API key in EMO AI, it does **not** save it to a file. Instead, it stores it in your computer's **operating system keychain** — the same secure system used by your browser to save passwords.

### How It Works on Each Platform

| Platform | Keychain Name | How to View Your Keys |
|---|---|---|
| **macOS** | Keychain Access (in Applications → Utilities) | Open Keychain Access → search for "emo-desktop" |
| **Windows** | Credential Manager (Control Panel → User Accounts) | Open Credential Manager → Windows Credentials → look for "emo-desktop" |
| **Linux** | libsecret (GNOME Keyring / KDE Wallet) | Use your system's password manager |

### Why This Matters

- **No configuration files.** Your keys are never sitting in a `.json`, `.env`, or `.txt` file that could be accidentally shared or backed up.
- **Encrypted at rest.** Keychains encrypt data using your system's hardware security.
- **App-specific.** Only EMO AI can read its own entries. Other apps can't access them.
- **No visible display.** Once entered, your key is never shown again in the app. If you need to change it, you type a new one — the old one is replaced automatically.

> **Screenshot:** `screenshots/keychain-mac.png` — macOS Keychain Access showing "emo-desktop" entry
> **Screenshot:** `screenshots/keychain-win.png` — Windows Credential Manager showing stored credential

### What If the Keychain Is Unavailable?

EMO AI **will not start** if the system keychain is unavailable. This is by design — there is no fallback, no file-based cache, no workaround. Your keys require the keychain's protection.

---

## Data Privacy — Where Your Information Lives

### What We Store

| Data | Where | Can You Delete It? |
|---|---|---|
| API Keys | Your computer's keychain (local) | Yes — remove in Settings → Providers |
| Project Memory | Your computer (local storage) | Yes — clear per-project or globally |
| Knowledge Files | Your computer (local storage) | Yes — delete from Knowledge Base |
| Agent Results | Your computer (local storage) | Yes — delete from project feed |
| Usage Statistics | Anonymized, transmitted only for billing | Contact support for deletion |
| Account Email | Our secure servers | Yes — via account settings |

### What We NEVER Store

- Your API keys (they never leave your machine)
- The content of your agent prompts (processed locally)
- Your files or documents (stored only on your computer)
- Your browsing history, contacts, or personal data

### Data Deletion Policy

- **Local data:** Delete anytime from the app. Or uninstall EMO AI — all local data is removed.
- **Account data:** Email support@emo-ai.dev with a deletion request. We process within 30 days.

---

## Permissions — What Agents Can and Can't Do

Every agent in EMO AI runs inside a **sandbox** — a restricted environment that limits what it can access.

### Sandbox Limits

| Resource | Limit | Why |
|---|---|---|
| CPU usage | 50% max | Prevents any single agent from slowing your computer |
| Memory | 512 MB max | Keeps the app responsive |
| Network requests | 100 per minute | Prevents runaway background activity |
| File access | Project files only | Agents can't read your documents, photos, or system files |
| Command execution | Allowed commands only | Agents can't run shell commands or install software |

### What Agents Can Access

- Your project's **Knowledge Base** (files you explicitly added)
- Your project's **Memory** (information the project has learned)
- The AI provider you connected (via your API key)

### What Agents CANNOT Access

- Other projects' data
- Your personal files (Documents, Desktop, etc.)
- System settings or other applications
- The internet beyond what's needed for their task
- Your API key (they see only the connection, not the key string)

---

## Updates — How EMO AI Stays Safe

### Verified Updates

Every update to EMO AI is **digitally signed** before it reaches you.

- **macOS:** Code-signed by Apple-notarized certificates.
- **Windows:** Signed with Authenticode (Microsoft-trusted).
- **Linux:** Signed with GPG (detached signature verified automatically).

### What Happens During an Update

1. EMO AI checks for updates at [releases.emo-ai.dev](https://releases.emo-ai.dev).
2. It downloads the update manifest (a file containing the version, signature, and checksum).
3. It verifies the signature against the public key built into the app.
4. If the signature is valid, the update is installed.
5. If the signature is missing or invalid, the update is **rejected** — no prompt, no install.

### Safe Rollback

If an update causes issues:
1. Open **Settings** → **Updates** → **Version History**.
2. Click **Rollback** next to the previous version.
3. The previous version is reinstalled. Your data is preserved.

---

## Privacy Checklist

- [ ] API keys stored in OS keychain only
- [ ] No keys in log files, config files, or backups
- [ ] Agent sandbox limits active and enforced
- [ ] Updates verified by signature before install
- [ ] Local data deletable at any time
- [ ] Account data deletable on request

---

## Reporting a Security Issue

If you find a security vulnerability, please email **security@emo-ai.dev**. Do not post it publicly. We aim to respond within 48 hours.

---

# دليل الأمان والخصوصية — EMO AI

> كيف تبقى بياناتك آمنة، أين تُخزّن مفاتيحك، وما لا نراه أبداً.

---

## تخزين المفاتيح — كيف يحمي EMO AI مفاتيح API الخاصة بك

عند إدخال مفتاح API في EMO AI، فإنه **لا** يحفظه في ملف. بدلاً من ذلك، يُخزّنه في **سلسلة المفاتيح** بنظام التشغيل — نفس النظام الآمن الذي يستخدمه متصفحك لحفظ كلمات المرور.

| النظام | اسم سلسلة المفاتيح |
|---|---|
| **ماك** | Keychain Access (التطبيقات → الأدوات المساعدة) |
| **ويندوز** | Credential Manager (لوحة التحكم → حسابات المستخدمين) |
| **لينكس** | libsecret (GNOME Keyring / KDE Wallet) |

### لماذا هذا مهم

- **لا ملفات إعدادات.** مفاتيحك ليست في ملف `.json` أو `.env` قد يُشارك أو يُنسخ احتياطياً عن طريق الخطأ.
- **مشفرة.** سلسلة المفاتيح تشفّر البيانات باستخدام أمان جهازك.
- **خاصة بالتطبيق.** فقط EMO AI يمكنه قراءة مدخلاته.
- **غير مرئية.** بمجرد إدخال المفتاح، لا يظهر مرة أخرى في التطبيق.

### ماذا لو كانت سلسلة المفاتيح غير متاحة؟

لن يعمل EMO AI إذا كانت سلسلة المفاتيح غير متاحة. لا يوجد حل بديل — مفاتيحك تتطلب حماية سلسلة المفاتيح.
