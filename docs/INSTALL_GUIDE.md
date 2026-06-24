# EMO AI — Installation Guide

## Installation Guide v1.0

> **Version:** 1.0.0-RC18
> **Last Updated:** 2026-06-24

---

## Prerequisites

### Required
- Python 3.12 or higher
- pip package manager
- Git

### Optional (Production)
- PostgreSQL 14+ (SQLite by default)
- Docker & Docker Compose
- Qdrant (for vector DB production backend)
- Redis (for distributed rate limiting)

---

## Quick Start (Development)

### 1. Clone the Repository

```bash
git clone https://github.com/emam2025/EMO-AI-Execution-OS.git
cd EMO-AI-Execution-OS
```

### 2. Create Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate  # Linux/macOS
# or on Windows:
# .venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your settings:

```env
# Required
EMO_JWT_SECRET=your-secure-jwt-secret-min-32-chars
EMO_AUDIT_SIGNING_KEY=your-audit-signing-key

# LLM Provider (choose one)
LLM_PROVIDER=openrouter  # or: groq, gemini, ollama
OPENROUTER_API_KEY=your-api-key

# Database (optional, defaults to SQLite)
# DATABASE_URL=postgresql://user:pass@localhost:5432/emo_ai
EMO_DB_PATH=emo_ai.db

# Vector DB (optional)
# EMO_VECTOR_BACKEND=qdrant
# QDRANT_URL=http://localhost:6333
```

### 5. Initialize Database

```bash
python3 -c "
import asyncio
from core.db import db
asyncio.run(db.initialize())
print('Database initialized')
"
```

### 6. Run the Server

```bash
uvicorn main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`

---

## Production Installation

### Using Docker Compose

```bash
# Set required environment variables
export EMO_JWT_SECRET="your-secure-secret"
export EMO_AUDIT_SIGNING_KEY="your-audit-key"

# Start services
docker-compose up -d
```

### Using PostgreSQL

1. Install PostgreSQL 14+
2. Create database:
   ```sql
   CREATE DATABASE emo_ai;
   CREATE USER emo_user WITH PASSWORD 'secure-password';
   GRANT ALL PRIVILEGES ON DATABASE emo_ai TO emo_user;
   ```
3. Set environment:
   ```env
   DATABASE_URL=postgresql://emo_user:secure-password@localhost:5432/emo_ai
   ```

### Using Qdrant (Vector DB)

1. Run Qdrant:
   ```bash
   docker run -d --name emo-qdrant -p 6333:6333 qdrant/qdrant:latest
   ```
2. Set environment:
   ```env
   EMO_VECTOR_BACKEND=qdrant
   QDRANT_URL=http://localhost:6333
   ```
3. Install optional dependency:
   ```bash
   pip install qdrant-client>=1.9.0
   ```

---

## Verification

### Run Tests

```bash
# Full test suite
pytest tests/ -q

# Count tests
pytest tests/ --collect-only -q | tail -1
```

### Check API Health

```bash
curl http://localhost:8000/health
```

### Verify Security

```bash
# Check JWT secret is set
echo $EMO_JWT_SECRET

# Verify auth mode
echo $EMO_AUTH_MODE  # should be "enforced" in production
```

---

## Troubleshooting

### Common Issues

#### ModuleNotFoundError: No module named 'aiosqlite'
```bash
pip install aiosqlite
```

#### ModuleNotFoundError: No module named 'openai'
```bash
pip install openai
```

#### Database locked errors
- Use PostgreSQL for production (SQLite has write limitations)
- Ensure only one process writes to SQLite

#### Tests fail with collection errors
```bash
# Ensure .ai/logs directory exists
mkdir -p .ai/logs

# Reinstall dependencies
pip install -r requirements.txt
```

### Getting Help

- Check [CHANGELOG.md](../CHANGELOG.md) for recent changes
- Review [docs/EMO_AI_MASTER_ARCHITECTURE_REFERENCE.md](EMO_AI_MASTER_ARCHITECTURE_REFERENCE.md)
- Open an issue on GitHub

---

## Next Steps

- Read the [User Guide](USER_GUIDE.md)
- Review [Architecture Reference](EMO_AI_MASTER_ARCHITECTURE_REFERENCE.md)
- Check [Development Plan](../EMO_AI_DEVELOPMENT_PLAN.md) for roadmap
