# Dermatology Bridge

> For clinician review — not a diagnosis.

Dermatology Bridge is a clinician-facing longitudinal skin decision-support platform. It captures patient photos during clinic visits, stores them privately, compares them over time, and produces a structured consultation report for clinician review.

## Core principles

- Mock-first defaults to protect API budgets and avoid accidental live calls.
- Private images are stored in private storage and accessed through short-lived signed URLs.
- Concern definitions are frozen and versioned to keep longitudinal comparisons consistent.
- Narrative output is grounded in structured numeric data rather than raw images.
- All outputs carry the required clinical caution: For clinician review — not a diagnosis.

## Repository structure

- `apps/api` — FastAPI backend, SQLAlchemy models, JWT auth, storage logic, and report generation
- `apps/web` — Next.js frontend for clinician workflows and patient enrollment
- `docs/` — project notes, API contract, and deployment guidance
- `fixtures/` — sample payloads and synthetic analysis data
- `templates/` — PDF and narrative report templates

## Local development

### API

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate   # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
alembic upgrade head
python -m app.scripts.seed
uvicorn app.main:app --reload
```

### Web app

```bash
cd apps/web
npm install
npm run dev
```

The frontend expects the API to be available at the configured backend URL, typically `http://localhost:8000` during local development.

## Production deployment on Vercel

This repository is designed to deploy as a single Vercel project with two services:

- `apps/web` → Next.js frontend
- `apps/api` → FastAPI backend

The root `vercel.json` config routes `/api/*`, `/auth/*`, and `/health` to the API service, while all other routes go to the frontend.

### Required deployment requirements

Before importing to Vercel:

1. Rotate any credentials that were committed or shared in local files.
2. Use Supabase Postgres or another managed Postgres service for the database.
3. Use private S3-compatible storage for patient photos and masks; do not use local filesystem for production.
4. Use a unique JWT secret for all non-local environments.
5. Keep `ALLOW_LIVE_CALLS=false` unless a real YouCam production key is intentionally configured and approved.

### Recommended environment variables

Set these in the Vercel project environment variables for the API service:

- `DATABASE_URL`
- `JWT_SECRET_KEY`
- `ALLOW_LIVE_CALLS=false`
- `YOUCAM_API_KEY`
- `YOUCAM_BASE_URL`
- `STORAGE_BACKEND=s3`
- `STORAGE_BUCKET`
- `STORAGE_ENDPOINT_URL`
- `STORAGE_ACCESS_KEY_ID`
- `STORAGE_SECRET_ACCESS_KEY`
- `STORAGE_REGION`
- `CORS_ORIGINS` (only when a different frontend origin is used)

Do not store secrets in `NEXT_PUBLIC_*` variables.

### Deployment notes

- Import the repository root, not `apps/`.
- Keep the root `vercel.json` file in place.
- Configure the API service with the FastAPI entrypoint `app.main:app`.
- Run Alembic migrations against the production database before serving live traffic.
- Verify `/health`, login, patient creation, upload capture, and chart deletion in a staging environment before using real patient data.

## Privacy and compliance

This project handles medical and clinical information. Before any production deployment:

- confirm your data retention policy
- confirm storage encryption and access controls
- confirm patient consent and deletion workflow requirements
- confirm the hosting provider’s privacy and compliance posture

## Cost notes

Vercel Hobby can be a good starting point for low-volume projects, but production medical workloads often require paid tiers for database, object storage, and bandwidth. YouCam and storage charges are separate from Vercel fees.

## Resources

- `docs/deployment-vercel.md` — Vercel-specific deployment notes
- `docs/api-contract.md` — API expectations and payload formats
- `docs/` — project design and operational notes

---

This project is intended for clinician review workflows and not for autonomous diagnosis or patient-facing decision-making.
