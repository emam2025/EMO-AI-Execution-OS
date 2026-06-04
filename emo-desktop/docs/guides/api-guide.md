# EMO AI — API Guide (Simplified)

> For developers who want to integrate with EMO AI programmatically.
> No internal architecture — just endpoints, examples, and limits.

---

## Authentication

All API requests require a **Bearer token**. Generate one from your EMO AI account:

1. Open **Settings** → **API Tokens**.
2. Click **+ New Token**.
3. Give it a name (e.g., "CI Pipeline").
4. Copy the token immediately — it won't be shown again.

### Using Your Token

Include it in every request as an HTTP header:

```
Authorization: Bearer emo_api_xxxxxxxxxxxx
```

---

## Endpoints

### Base URL

```
https://api.emo-ai.dev/v1
```

---

### List Projects

**GET** `/api/projects`

Returns all projects you have access to.

**cURL:**
```bash
curl -H "Authorization: Bearer emo_api_xxxxxxxxxxxx" \
  https://api.emo-ai.dev/v1/api/projects
```

**Python:**
```python
import requests

headers = {"Authorization": "Bearer emo_api_xxxxxxxxxxxx"}
response = requests.get("https://api.emo-ai.dev/v1/api/projects", headers=headers)
print(response.json())
```

**Response:**
```json
{
  "projects": [
    {
      "id": "proj_abc123",
      "name": "Marketing Research",
      "agent_count": 3,
      "created_at": "2026-05-01T00:00:00Z"
    }
  ]
}
```

---

### Run an Agent

**POST** `/api/agents/run`

Starts an agent in a project and returns the result.

**cURL:**
```bash
curl -X POST \
  -H "Authorization: Bearer emo_api_xxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "proj_abc123",
    "instruction": "Summarize our Q2 competitor analysis"
  }' \
  https://api.emo-ai.dev/v1/api/agents/run
```

**Python:**
```python
import requests

headers = {"Authorization": "Bearer emo_api_xxxxxxxxxxxx"}
payload = {
    "project_id": "proj_abc123",
    "instruction": "Summarize our Q2 competitor analysis"
}
response = requests.post(
    "https://api.emo-ai.dev/v1/api/agents/run",
    headers=headers,
    json=payload
)
print(response.json())
```

**Response:**
```json
{
  "run_id": "run_xyz789",
  "status": "completed",
  "result": "Competitor analysis summary text...",
  "elapsed_seconds": 12.4
}
```

---

### Get Results

**GET** `/api/results/{run_id}`

Retrieves the result of a specific agent run.

**cURL:**
```bash
curl -H "Authorization: Bearer emo_api_xxxxxxxxxxxx" \
  https://api.emo-ai.dev/v1/api/results/run_xyz789
```

**Python:**
```python
import requests

headers = {"Authorization": "Bearer emo_api_xxxxxxxxxxxx"}
response = requests.get(
    "https://api.emo-ai.dev/v1/api/results/run_xyz789",
    headers=headers
)
print(response.json())
```

**Response:**
```json
{
  "run_id": "run_xyz789",
  "project_id": "proj_abc123",
  "status": "completed",
  "result": "Competitor analysis summary text...",
  "created_at": "2026-05-30T12:00:00Z",
  "elapsed_seconds": 12.4
}
```

---

### List Knowledge Files

**GET** `/api/projects/{project_id}/knowledge`

Returns all knowledge files in a project.

**cURL:**
```bash
curl -H "Authorization: Bearer emo_api_xxxxxxxxxxxx" \
  https://api.emo-ai.dev/v1/api/projects/proj_abc123/knowledge
```

---

## Quick Reference

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/projects` | List all projects |
| POST | `/api/agents/run` | Run an agent in a project |
| GET | `/api/results/{run_id}` | Get agent run result |
| GET | `/api/projects/{id}/knowledge` | List knowledge files |
| POST | `/api/projects` | Create a new project |
| DELETE | `/api/projects/{id}` | Delete a project |

---

## Rate Limits

| Tier | Requests per minute | Requests per day |
|---|---|---|
| Free | 10 | 500 |
| Pro | 60 | 10,000 |
| Enterprise | 300 | 100,000 |

**When you exceed a limit:**
```json
{
  "error": "rate_limit_exceeded",
  "retry_after_seconds": 30
}
```

Wait for the specified time before retrying.

---

## Error Codes

| Code | Meaning | What to Do |
|---|---|---|
| `invalid_token` | Token is missing or expired | Generate a new token from Settings |
| `project_not_found` | Project ID doesn't exist | Check your project list |
| `agent_busy` | Too many agents running | Wait and retry |
| `rate_limit_exceeded` | Too many requests | Wait for `retry_after_seconds` |
| `internal_error` | Something went wrong on our side | Retry after a few seconds |

---

## Best Practices

1. **Cache project IDs** — they don't change, so store them after fetching once.
2. **Handle rate limits** — check the `retry_after_seconds` field and pause accordingly.
3. **Use descriptive instruction text** — clearer instructions produce better results.
4. **Set reasonable timeouts** — most agent runs complete within 30 seconds. Set a 60-second timeout.
5. **Store tokens securely** — treat tokens like passwords. Use environment variables, not hardcoded strings.
