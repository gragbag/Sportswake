# A target listed here runs even when a file or directory shares its name
# (eval/ was silently shadowing `make eval`). The backslash must be the LAST
# character on the line -- text after it detaches the continuation.
.PHONY: check lint types migrations imports fmt db-up db-migrate db-refresh \
        embed cluster report recluster ingest branch eval \
        api web web-build summarize summarize-dry moderate \
        categorize categorize-dry evict

VENV     := .venv/bin
LOCAL_DB := postgresql://postgres:postgres@localhost:5432/presswake

# Targets run against Supabase by default: no DATABASE_URL is set here, so
# python-dotenv loads it from .env. Add LOCAL=1 for the Docker database:
#     make api            Supabase -- the real corpus
#     make api LOCAL=1    Docker scratch
#
# One consequence to keep in mind: `make db-migrate` now alters the PRODUCTION
# schema. That is usually what you want (prod is the only database that has to
# be current), but a migration you have not tested lands on real data with no
# undo. Test new migrations with `make db-migrate LOCAL=1` first.
DB :=
ifdef LOCAL
DB := DATABASE_URL=$(LOCAL_DB)
endif

# ---- what CI runs -----------------------------------------------------
check: lint imports types migrations

lint:
	$(VENV)/ruff check .

imports:
	$(VENV)/python -c "import common.models, worker.ingest, worker.summarize, worker.moderate, worker.categorize, app.main"

types:
	$(VENV)/mypy common worker app

migrations:
	$(VENV)/alembic check

fmt:
	$(VENV)/ruff format .
	$(VENV)/ruff check --fix .

# ---- local database ---------------------------------------------------
db-up:
	docker start presswake-db 2>/dev/null || docker run -d --name presswake-db \
	  -p 5432:5432 -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=presswake \
	  pgvector/pgvector:pg16

db-migrate:
	$(DB) $(VENV)/alembic upgrade head

# Pull the real corpus down into Docker so local experiments run on current
# data. Copies outlets and articles only -- stories are derived, so rebuild
# them with `make recluster`. The script refuses any target but localhost,
# so this cannot run backwards.
db-refresh:
	DATABASE_URL=$(LOCAL_DB) $(VENV)/python scripts/copy_from_supabase.py \
	  "$$(grep -E '^DATABASE_URL=' .env | cut -d= -f2-)"

# ---- pipeline (local by default; PROD=1 for Supabase) ------------------
ingest:
	$(DB) $(VENV)/python -m worker.ingest

embed:
	$(DB) $(VENV)/python -m worker.embed

cluster:
	$(DB) $(VENV)/python -m worker.cluster

report:
	$(DB) $(VENV)/python scripts/cluster_report.py

# Hard-wired to Docker, no LOCAL=1 needed and no PROD escape hatch: the whole
# point is the --reset, and cluster.py refuses that off localhost. Pointed at
# Supabase it would skip the reset and quietly cluster only pending articles
# -- a different operation wearing the same name. This is the threshold-tuning
# loop (recluster -> report -> eval), so it belongs on scratch data anyway.
recluster:
	DATABASE_URL=$(LOCAL_DB) $(VENV)/python -m worker.cluster --reset
	DATABASE_URL=$(LOCAL_DB) $(VENV)/python scripts/cluster_report.py

branch:
	git switch main
	git pull --ff-only --prune
	git switch -c $(name)

eval:
	$(DB) $(VENV)/python scripts/eval_clustering.py

# ---- summaries (milestone 5) -------------------------------------------
# dry first: prints what it WOULD write, calls the LLM, touches nothing.
summarize-dry:
	$(DB) $(VENV)/python -m worker.summarize --dry-run --limit 5

summarize:
	$(DB) $(VENV)/python -m worker.summarize

# Assign categories. Dry first: prints what it WOULD tag, writes nothing.
categorize-dry:
	$(DB) $(VENV)/python -m worker.categorize --dry-run --limit 15

categorize:
	$(DB) $(VENV)/python -m worker.categorize

# Drop cluster members that are temporally isolated from their story --
# cleanup for stories built before the MAX_MEMBER_GAP_DAYS ceiling existed.
# Dry by default, unlike the workers above: this one DELETEs. Add APPLY=1.
evict:
	$(DB) $(VENV)/python scripts/evict_outliers.py $(if $(APPLY),--apply,)

# Resolve comments that could not be classified when they were posted.
moderate:
	$(DB) $(VENV)/python -m worker.moderate

# ---- frontend ----------------------------------------------------------
api:
	$(DB) $(VENV)/uvicorn app.main:app --reload --port 8000

web:
	npm --prefix frontend run dev

web-build:
	npm --prefix frontend run build
