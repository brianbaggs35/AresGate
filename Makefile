# AresGate: `make` lists every command.
SHELL := /bin/bash
BACKEND := cd backend &&
FRONTEND := cd frontend &&
ACTIONLINT_IMAGE := rhysd/actionlint:1.7.12
# Run from its image, pinned by digest, rather than a third-party GitHub Action.
TRIVY_IMAGE := aquasec/trivy:0.76.0@sha256:2416d1f74045b57274df1a340eee6b510cacd73c66a6ccb8da092b117eb7d222
TRIVY := docker run --rm -v aresgate-trivy-cache:/root/.cache/trivy
TRIVY_FLAGS := --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1
# pytest runs on a throwaway Postgres, the same image CI tests on. It only listens on this
# computer and is removed afterwards, so it has no password.
TEST_DB_IMAGE := postgres:18
TEST_DB := aresgate-test-db
TEST_DB_PORT ?= 55432

.DEFAULT_GOAL := help
.PHONY: help dev-api dev-web install test test-backend test-frontend \
	lint lint-backend lint-frontend lint-infra format audit scan scan-source clean

help: ## Show this help
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_-]+:.*## / {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

## ---- Develop -------------------------------------------------------------------
dev-api: ## Run the API with live reload on http://127.0.0.1:8000 (needs ARESGATE_DATABASE_URL)
	$(BACKEND) uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

dev-web: ## Run the web app with live reload on http://127.0.0.1:5173, proxying /api to the API
	$(FRONTEND) npm run dev

install: ## Install backend and frontend dependencies locally
	$(BACKEND) uv sync
	$(FRONTEND) npm ci --ignore-scripts

test: test-backend test-frontend ## Run all tests with coverage (95% minimum; 100% target)

test-backend: ## Run pytest with coverage, on a throwaway Postgres
	@docker rm --force $(TEST_DB) >/dev/null 2>&1 || true
	docker run --detach --rm --name $(TEST_DB) --publish 127.0.0.1:$(TEST_DB_PORT):5432 \
		--env POSTGRES_USER=aresgate --env POSTGRES_HOST_AUTH_METHOD=trust $(TEST_DB_IMAGE) >/dev/null
	@# Over TCP, which only opens once the image's first-start setup has finished.
	@for _ in $$(seq 60); do \
		docker exec $(TEST_DB) pg_isready --quiet -h 127.0.0.1 -U aresgate && break; sleep 1; \
	done
	@$(BACKEND) ARESGATE_TEST_DATABASE_URL=postgresql+psycopg://aresgate@127.0.0.1:$(TEST_DB_PORT)/aresgate \
		uv run pytest; status=$$?; docker rm --force $(TEST_DB) >/dev/null; exit $$status

test-frontend: ## Run vitest with coverage
	$(FRONTEND) npm run coverage

## ---- Check ---------------------------------------------------------------------
lint: lint-backend lint-frontend lint-infra ## Run every linter and type checker

lint-backend: ## ruff, pyright and bandit
	$(BACKEND) uv run ruff check . && uv run ruff format --check . \
		&& uv run pyright && uv run bandit -c pyproject.toml -r app migrations -q

lint-frontend: ## ESLint, Prettier and vue-tsc
	$(FRONTEND) npm run lint -- --max-warnings=0 && npm run format:check && npm run typecheck

lint-infra: ## actionlint (CI workflows)
	docker run --rm -v "$(CURDIR):/repo:ro" -w /repo $(ACTIONLINT_IMAGE) -color

format: ## Auto-format backend and frontend code
	$(BACKEND) uv run ruff check --fix . && uv run ruff format .
	$(FRONTEND) npm run lint -- --fix && npm run format

audit: ## Check dependencies for known vulnerabilities (the frontend fails on critical, as CI does)
	$(BACKEND) uv run pip-audit
	$(FRONTEND) npm audit --audit-level=critical

scan: scan-source ## Scan the code with Trivy

scan-source: ## Trivy: vulnerable dependencies, leaked secrets and configuration mistakes
	$(TRIVY) -v "$(CURDIR):/src:ro" -w /src $(TRIVY_IMAGE) fs $(TRIVY_FLAGS) \
		--scanners vuln,secret,misconfig .

clean: ## Remove local build and test artifacts
	rm -rf backend/.pytest_cache backend/.ruff_cache backend/.coverage \
		backend/coverage.xml frontend/dist frontend/coverage
