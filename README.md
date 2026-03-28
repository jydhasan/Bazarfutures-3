# BazarFutures — ভবিষ্যতের বাজার

Bangladesh's first agricultural futures contract platform.

## Quick Start with Docker

```bash
git clone <repo>
cd bazarfutures
cp .env.example .env
docker compose up --build
```

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- pgAdmin: http://localhost:5050

## Stack
- **Frontend**: HTML/CSS/JS (Nginx)
- **Backend**: FastAPI + Python 3.12
- **Database**: PostgreSQL 16
- **Cache**: Redis 7
- **Task Queue**: APScheduler (daily price update)
- **Reverse Proxy**: Nginx
