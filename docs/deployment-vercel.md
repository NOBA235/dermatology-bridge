# Deploying the web app and API on Vercel

The repository root `vercel.json` declares two Vercel Services: Next.js at
`apps/web` and FastAPI at `apps/api`. Requests to `/api/*`, `/auth/*`, and
`/health` are routed to FastAPI; other paths are routed to Next.js. The browser
API client uses the same deployed origin by default, so no public API URL is
needed for the grouped deployment.

## Before importing

1. Rotate any credentials that have been shared or committed. Use fresh,
   unique values for database, YouCam, storage, and JWT secrets.
2. Set the Supabase Storage bucket to **private**. Create a bucket-scoped S3
   access key where possible; never use a public bucket or put secret values in
   `NEXT_PUBLIC_*` variables.
3. Use a Supabase Postgres connection-pooler URL appropriate for serverless
   clients, and ensure the Vercel deployment can connect to it.
4. Ensure the YouCam integration is intentionally enabled. Start with
   `ALLOW_LIVE_CALLS=false`; switching it to `true` can incur third-party API
   usage charges.

## Vercel import

Import the Git repository as one project from the **repository root**. Keep
the root `vercel.json`; do not set the project's root directory to `apps/`,
because the service roots in that file are relative to the repository root.
Vercel Services builds the two app roots independently.

Add these environment variables to the **API service only**, for Production
and Preview as appropriate:

- `DATABASE_URL` — fresh Supabase pooler connection string.
- `JWT_SECRET_KEY` — unique random secret, at least 32 random bytes.
- `STORAGE_BACKEND=s3`
- `STORAGE_BUCKET`
- `STORAGE_ENDPOINT_URL`
- `STORAGE_ACCESS_KEY_ID`
- `STORAGE_SECRET_ACCESS_KEY`
- `STORAGE_REGION` — use the region required by the storage provider (often
  `us-east-1` for Supabase S3-compatible storage).
- `ALLOW_LIVE_CALLS=false` initially; set a fresh `YOUCAM_API_KEY` and the
  approved `YOUCAM_BASE_URL` before opting in to live calls.
- `SEED_CLINICIAN_EMAIL` and `SEED_CLINICIAN_PASSWORD` only if you deliberately
  run the seed script; never use the demo password in production.

`CORS_ORIGINS` is only needed if the browser calls an API on a different
origin; use a comma-separated allowlist of exact HTTPS origins. The grouped
same-origin routing normally does not require CORS configuration.

Run the Alembic migrations against the target database before sending traffic.
Do not run migrations at every function startup. Verify `/health`, sign-in,
chart creation, image capture, and patient deletion with synthetic data before
using any real patient information.

## Storage behavior

Local development and tests continue to use local disk. On Vercel, the API
refuses to start unless S3-compatible private storage is configured; Vercel's
function filesystem is not durable. The S3 storage implementation is used for
uploaded photos and masks, PDF report mask reads, and deleting a patient's
objects when their chart is deleted.

## Cost and plan notes

Vercel Hobby is free within its published quotas, but is limited to personal,
non-commercial use. A clinician-facing or commercial deployment may require
Vercel Pro. Database, object storage, domain, and YouCam charges are separate;
check their current plans and usage limits before launch. The app contains
health-related information, so confirm appropriate contractual, privacy, and
compliance requirements with each provider before storing real patient data.