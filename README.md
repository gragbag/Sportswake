# Sportswake

An NBA news aggregator. It clusters articles from many outlets into single
stories and shows how coverage differed — who published, when, and who didn't.

## Prerequisites

- Python 3.12
- Node 22+
- A database: the shared Supabase project (ask for credentials) **or** Docker
  for a local scratch database

## Setup

```bash
# Python — app deps, dev tooling, then the ML deps for the embed worker.
# CPU torch must be installed FIRST and from PyTorch's own index, or
# sentence-transformers pulls the ~2 GB CUDA build.
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/pip install torch==2.13.0 --index-url https://download.pytorch.org/whl/cpu
.venv/bin/pip install -r requirements-worker.txt

# Frontend
npm --prefix frontend ci
```

## Configure

Create `.env` in the repo root (it is gitignored — never commit it):

```bash
# Supabase SESSION pooler string — port 5432, username postgres.<project-ref>.
# Not the transaction pooler (6543): DDL breaks there. Not the direct string:
# IPv6-only, and its plain `postgres` username silently disables auth.
DATABASE_URL=postgresql://postgres.<ref>:<password>@<region>.pooler.supabase.com:5432/postgres

# Supabase dashboard -> Project Settings -> API. Safe for browser code;
# used only for sign-in. Never put a secret behind a VITE_ prefix.
VITE_SUPABASE_URL=https://<ref>.supabase.co
VITE_SUPABASE_ANON_KEY=<anon-or-publishable-key>

# Optional. Without them the workers print a skip message and exit cleanly.
GROQ_API_KEY=      # story summaries + category/team tagging
OPENAI_API_KEY=    # comment moderation
```

No Supabase access? Run everything against Docker instead: `make db-up`
starts a pgvector Postgres, then add `LOCAL=1` to every make target below
(`make db-migrate LOCAL=1`, `make ingest LOCAL=1`, ...).

## Build the schema and get data

```bash
make db-migrate   # alembic upgrade head — the whole schema, seeded
make ingest       # fetch the RSS feeds -> articles
make embed        # embed new articles (downloads the model on first run)
make cluster      # group articles into stories, then merge near-duplicates
make categorize   # optional, needs GROQ_API_KEY: category + team tags
```

Every step is incremental and idempotent — re-running is always safe.

## Run

Two terminals:

```bash
make api    # FastAPI on :8000
make web    # Vite dev server — open the URL it prints, at /app/
```

The dev server proxies `/api/*` to :8000, so there is no CORS to configure.

## Checks

`make check` runs everything CI runs: lint, type-checking, import smoke
test, and `alembic check`. Run it before pushing.

## Production

Nothing here needs to be deployed by hand. A GitHub Action ingests hourly
(migrations → ingest → embed → cluster → summarize → categorize → moderate;
story merging runs on a separate daily schedule), and the API + frontend
deploy on Render. Scheduled workflows only fire from `main`.
