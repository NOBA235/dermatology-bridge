# Dermatology Bridge

> **For clinician review — not a diagnosis.**

**YouCam powers try-on for 800+ consumer brands; this is the bridge to the clinic.**

Dermatology Bridge is a clinician-facing longitudinal skin decision-support tool built on the YouCam Skin AI API. Patients capture guided selfies at clinic visits; the platform records immutable YouCam skin concern analyses across visits, computes treatment-response flags against a baseline, and renders a structured 3-page consultation PDF report.

## Non-Negotiable Principles

- **Mock-first**: `ALLOW_LIVE_CALLS=false` is enforced by default to preserve the 1,000-unit API budget.
- **Private images**: Patient selfies and masks are stored in private storage and accessed via short-lived signed URLs. Selfies are never stored publicly and are deletable on request.
- **Frozen concern list**: The 12 YouCam skin concern actions are versioned via `visits.analysis_version`.
- **Grounded agent**: The narrative layer only reads structured JSON, never sees patient images, and validates every emitted number against `concern_scores` before display.
- **Hedged clinical language**: All outputs carry the mandatory notice: *"For clinician review — not a diagnosis."*

## Monorepo Structure

- `apps/api` — FastAPI + SQLAlchemy 2.x + Pydantic v2 + Alembic backend
- `apps/web` — Next.js 14 App Router + TypeScript + Tailwind CSS frontend
- `docs/` — Architecture, API contract, and technical debt records
- `fixtures/` — Mock YouCam payloads and synthetic test fixtures

## Phase 0 Quickstart

### Backend (`apps/api`)

```bash
cd apps/api
pip install -e ".[dev]"
alembic upgrade head
python -m app.scripts.seed
uvicorn app.main:app --reload
```

### Frontend (`apps/web`)

```bash
cd apps/web
npm install
npm run dev
```
