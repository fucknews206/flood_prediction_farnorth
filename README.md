# AquaGuard AI — Cameroon Flood Intelligence System

AI-powered flood risk assessment and early warning system for Cameroon's Far North region.

## Table of Contents

- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Environment Configuration](#environment-configuration)
- [Database Setup](#database-setup)
- [Frontend](#frontend)
- [Backend](#backend)
- [Deployment](#deployment)
- [External APIs](#external-apis)
- [Troubleshooting](#troubleshooting)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Browser                              │
│                   React SPA (Vite)                          │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP/JSON
┌──────────────────────────▼──────────────────────────────────┐
│              FastAPI Backend (Python)                       │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │ Auth Layer  │  │ Far North    │  │ AI Agents         │  │
│  │ (OIDC/Local)│  │ Risk Engine  │  │ (NVIDIA/h2ogpte)  │  │
│  └─────────────┘  └──────────────┘  └───────────────────┘  │
└──────────────────────────┬──────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
┌───────▼──────┐  ┌───────▼──────┐  ┌───────▼──────┐
│ PostgreSQL   │  │    Redis     │  │ External APIs│
│ + PostGIS    │  │  (RQ jobs)   │  │ Open-Meteo   │
│              │  │              │  │ GloFAS       │
└──────────────┘  └──────────────┘  └──────────────┘
```

## Prerequisites

### Required
- **Node.js** >= 20
- **Python** >= 3.10
- **PostgreSQL** >= 14 with PostGIS extension
- **Redis** >= 6 (optional — for background jobs)

### Optional
- **NVIDIA API Key** — [build.nvidia.com](https://build.nvidia.com)
- **H2OGPTE Access** — [h2o.ai](https://h2o.ai/platform/enterprise-h2ogpte/)
- **GloFAS API Key** — [climate.copernicus.eu](https://climate.copernicus.eu/)

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/your-org/aquaguard-ai.git
cd aquaguard-ai
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your configuration
```

### 3. Start the backend

```bash
cd core
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.server.txt
uvicorn flood_prediction.server:app --reload --port 8000
```

### 4. Start the frontend

```bash
cd ui
npm install
npm run dev
```

The frontend will be available at `http://localhost:3000`.

## Environment Configuration

All environment variables use the `APP_` prefix for backend settings.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `APP_DATABASE_URL` | Yes | — | PostgreSQL connection string |
| `APP_REDIS_URL` | No | `redis://localhost:6379` | Redis connection for background jobs |
| `APP_NVIDIA_API_KEY` | No | — | NVIDIA AI API key |
| `APP_H2OGPTE_URL` | No | — | H2OGPTE endpoint URL |
| `APP_H2OGPTE_API_KEY` | No | — | H2OGPTE API key |
| `APP_GLOFAS_API_KEY` | No | — | Copernicus GloFAS API key |
| `APP_OIDC_AUTHORITY` | No | — | OIDC provider URL |
| `APP_OIDC_CLIENT_ID` | No | — | OIDC client ID |
| `APP_SECRET_KEY` | Yes (prod) | — | JWT signing secret |
| `APP_ENV` | No | `development` | Environment: development/production/test |
| `APP_CORS_ORIGINS` | No | `*` | Comma-separated allowed CORS origins |

### Frontend Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `VITE_API_BASE_URL` | No | `http://localhost:8000` | Backend API URL |
| `VITE_BASE_URL` | No | `/` | Base path for deployment |

## Database Setup

### PostgreSQL + PostGIS

```sql
CREATE DATABASE flood_prediction;
\c flood_prediction
CREATE EXTENSION postgis;
```

The application auto-creates tables on first run via SQLAlchemy `create_all`.

### Migrations

```bash
cd core
alembic upgrade head
```

## Frontend

### Development

```bash
cd ui
npm install
npm run dev
```

### Production Build

```bash
cd ui
npm run build
npm run preview
```

### Deployment

The frontend is a static SPA. Deploy `ui/dist/` to any static host:

- **GitHub Pages**: Set `VITE_BASE_URL=/repository-name/`
- **Netlify/Vercel**: Set `VITE_API_BASE_URL` to your backend URL
- **S3/CloudFront**: Upload `dist/` contents

## Backend

### Development

```bash
cd core
uvicorn flood_prediction.server:app --reload --port 8000
```

### Production

```bash
cd core
uvicorn flood_prediction.server:app --host 0.0.0.0 --port 8000 --workers 4
```

### Docker

```bash
docker build -t aquaguard-backend .
docker run -p 8000:8000 --env-file .env aquaguard-backend
```

## Deployment

### Deployment Architecture

| Component | Hosting | Notes |
|-----------|---------|-------|
| Frontend SPA | GitHub Pages / Netlify / S3 | Static files from `ui/dist/` |
| Backend API | Railway / Render / AWS ECS | FastAPI + uvicorn |
| Database | Managed PostgreSQL | Neon / Supabase / RDS |
| Redis | Managed Redis | Upstash / ElastiCache |

### GitHub Pages Deployment

1. Set `VITE_BASE_URL=/your-repo-name/` in build environment
2. Set `VITE_API_BASE_URL=https://your-backend.com`
3. Build: `npm run build`
4. Deploy `ui/dist/` to `gh-pages` branch

### Backend Deployment (Railway/Render)

1. Set all `APP_*` environment variables
2. Set `APP_ENV=production`
3. Set `APP_CORS_ORIGINS=https://your-frontend.com`
4. Deploy with `uvicorn flood_prediction.server:app`

## External APIs

| API | Purpose | Authentication |
|-----|---------|----------------|
| Open-Meteo | Weather forecast | None |
| GloFAS/Copernicus | River discharge | API key (optional) |
| RainViewer | Radar imagery | None |
| NASA OPERA | SAR flood imagery | None |
| NVIDIA NIM | AI inference | API key |
| H2OGPTE | AutoML | API key |

## Troubleshooting

### Database connection failed

Verify `APP_DATABASE_URL` is correct and PostgreSQL is running:
```bash
psql $APP_DATABASE_URL -c "SELECT 1"
```

### CORS errors

Set `APP_CORS_ORIGINS` to your frontend origin in production.

### ML model not found

The Far North risk engine is file-backed and does not require external model files. Training artifacts in `data_quality/` are for development only.

### Redis not available

The application works without Redis. Background jobs will be skipped. Set `APP_REDIS_URL` to enable them.
