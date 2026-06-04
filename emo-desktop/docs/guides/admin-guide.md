# EMO AI — Admin Guide

> Managing teams, projects, and permissions — no technical background required.

---

## User Management

### Adding Team Members

1. Open **Settings** → **Team**.
2. Click **+ Invite Member**.
3. Enter the person's email address.
4. Choose their role:
   - **Admin** — Full access to all projects, settings, and billing.
   - **Editor** — Can create and run agents, manage projects.
   - **Viewer** — Can see results and reports only.
5. Click **Send Invite**. They'll receive an email with setup instructions.

### Removing Team Members

1. Open **Settings** → **Team**.
2. Find the member and click the **✕** button.
3. Confirm removal. Their projects remain — reassign them if needed.

### Roles at a Glance

| Role | Create Projects | Run Agents | Manage Team | View Reports | Billing |
|---|---|---|---|---|---|
| Admin | ✓ | ✓ | ✓ | ✓ | ✓ |
| Editor | ✓ | ✓ | ✗ | ✓ | ✗ |
| Viewer | ✗ | ✗ | ✗ | ✓ | ✗ |

---

## Project Oversight

### Monitoring Resource Usage

Each project shows:
- **Active Agents** — How many agents are currently running.
- **Memory Size** — How much information the project has stored.
- **Usage This Month** — API calls made and estimated cost.

1. Go to the **Projects** dashboard.
2. Click any project to see its detailed usage.
3. Use the **Filter** bar to sort by most active or highest usage.

### Setting Limits

Admins can set per-project limits:
1. Open a project → **Settings** → **Limits**.
2. Set maximum **agents per project**, **memory size**, or **monthly API cost**.
3. When a limit is reached, the project pauses automatically. Admins receive a notification.

---

## Skill & Knowledge Management

### What are Knowledge Files?

Knowledge files are documents, notes, or reference materials your agents can use. Think of them as a shared library for your team.

### Adding Knowledge

1. Open a project → **Knowledge Base**.
2. Click **+ Add File**.
3. Upload a document (PDF, TXT, or Markdown).
4. Add a short description so your team knows what it contains.

### Managing Shared Memory

- **Project Memory** grows as agents work. You can review or clear it at any time.
- **Team Memory** is shared across all projects. Useful for company-wide knowledge.
- To clear memory: Project → **Memory** → **Clear** (or Team Settings → Team Memory → Clear).

---

## Audit & Compliance

### Reviewing Activity Logs

Every action in EMO AI is logged. To review:

1. Go to **Settings** → **Audit Log**.
2. Filter by:
   - **User** — See what a specific team member did.
   - **Action** — Login, project created, agent run, setting changed.
   - **Date Range** — Pick a time window.
3. Export the log as CSV for your records.

### What is Logged

- User logins and logouts
- Project creation and deletion
- Agent runs (who ran it, when, and the result size)
- API key changes (but never the key itself)
- Settings changes
- Update installations

> **Note:** EMO AI never logs your API keys, agent prompts, or agent results. Your work stays private.

---

## Billing & Plan Management

1. Go to **Settings** → **Billing**.
2. View your current plan, usage, and invoices.
3. To upgrade or downgrade, click **Change Plan**.
4. Enter payment information (secured and encrypted).

---

## Quick Reference for Admins

| Task | Where |
|---|---|
| Add team member | Settings → Team → + Invite Member |
| Set project limits | Project → Settings → Limits |
| View audit log | Settings → Audit Log |
| Manage knowledge | Project → Knowledge Base |
| Check billing | Settings → Billing |
| Clear team memory | Team Settings → Team Memory → Clear |
