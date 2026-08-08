# A target listed here runs even when a file or directory shares its name
# (eval/ was silently shadowing `make eval`). The backslash must be the LAST
# character on the line -- text after it detaches the continuation.
.PHONY: check lint types migrations imports fmt db-up db-migrate \
        embed cluster report recluster ingest branch eval \
        api web web-build summarize summarize-dry

VENV     := .venv/bin
LOCAL_DB := postgresql://postgres:postgres@localhost:5432/presswake

# ---- what CI runs -----------------------------------------------------
check: lint imports types migrations

lint:
	$(VENV)/ruff check .

imports:
	$(VENV)/python -c "import common.models, worker.ingest, worker.summarize, app.main"

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
	DATABASE_URL=$(LOCAL_DB) $(VENV)/alembic upgrade head

# ---- pipeline, always against the LOCAL database -----------------------
embed:
	DATABASE_URL=$(LOCAL_DB) $(VENV)/python -m worker.embed

cluster:
	DATABASE_URL=$(LOCAL_DB) $(VENV)/python -m worker.cluster

report:
	DATABASE_URL=$(LOCAL_DB) $(VENV)/python scripts/cluster_report.py

# the loop you have been running by hand
recluster:
	DATABASE_URL=$(LOCAL_DB) $(VENV)/python -m worker.cluster --reset
	DATABASE_URL=$(LOCAL_DB) $(VENV)/python scripts/cluster_report.py

branch:
	git switch main
	git pull --ff-only --prune
	git switch -c $(name)

eval:
	DATABASE_URL=$(LOCAL_DB) $(VENV)/python scripts/eval_clustering.py

# ---- summaries (milestone 5) -------------------------------------------
# dry first: prints what it WOULD write, calls the LLM, touches nothing.
summarize-dry:
	DATABASE_URL=$(LOCAL_DB) $(VENV)/python -m worker.summarize --dry-run --limit 5

summarize:
	DATABASE_URL=$(LOCAL_DB) $(VENV)/python -m worker.summarize

# ---- frontend ----------------------------------------------------------
api:
	DATABASE_URL=$(LOCAL_DB) $(VENV)/uvicorn app.main:app --reload --port 8000

web:
	npm --prefix frontend run dev

web-build:
	npm --prefix frontend run build
