# EMO AI Deployment Guide

## Prerequisites

- Docker & Docker Compose
- Python 3.14+
- Node.js 18+ (for web frontend)

## Local Development (Docker)

```bash
# Clone and start
git clone https://github.com/your-org/emo-ai.git
cd emo-ai
cp .env.example .env
# Edit .env with your settings
docker-compose up --build
```

- Backend: http://localhost:8000
- Web UI: http://localhost:3000

## Backend Deployment

### Railway

```bash
railway login
railway init
railway variables set EMO_JWT_SECRET=your_secret
railway variables set EMO_AUTH_MODE=migration
railway up
```

### Render

1. Connect GitHub repo
2. Set build command: `pip install -r requirements.txt`
3. Set start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Add environment variables

### Fly.io

```bash
fly auth login
fly launch
fly secrets set EMO_JWT_SECRET=your_secret
fly deploy
```

## Frontend Deployment (Vercel)

```bash
cd apps/web
vercel --prod
```

Set environment variable:
- `NEXT_PUBLIC_API_BASE_URL`: Your backend URL

## Required Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `EMO_JWT_SECRET` | JWT signing secret | (required) |
| `EMO_AUTH_MODE` | Auth mode | `migration` |
| `DATABASE_URL` | Database URL | `sqlite:///./data/emo_ai.db` |

## Security Notes

- Never commit `.env` files
- Use strong JWT secrets (32+ characters)
- Enable HTTPS in production
- Rotate secrets regularly
