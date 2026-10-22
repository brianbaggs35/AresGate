# AresGate: `make` lists every command.
SHELL := /bin/bash
COMPOSE := docker compose
DEV_COMPOSE := $(COMPOSE) -f docker-compose.yml -f docker-compose.dev.yml
E2E_COMPOSE := $(COMPOSE) -f docker-compose.e2e.yml
E2E_PORT := $${ARESGATE_E2E_PORT:-9443}
BACKEND := cd backend &&
FRONTEND := cd frontend &&
HADOLINT_IMAGE := hadolint/hadolint:v2.15.1
SHELLCHECK_IMAGE := koalaman/shellcheck:v0.11.0
ACTIONLINT_IMAGE := rhysd/actionlint:1.7.12
# Run from its image, pinned by digest, rather than a third-party GitHub Action.
TRIVY_IMAGE := aquasec/trivy:0.76.1@sha256:790fd66d1697395d8693d1acaa1ea702406a20f109b6fc7bac8db623eca6c06c
TRIVY := docker run --rm -v aresgate-trivy-cache:/root/.cache/trivy
TRIVY_FLAGS := --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1
# pytest runs on a throwaway Postgres, the same image CI tests on. It only listens on this
# computer and is removed afterwards, so it has no password.
TEST_DB_IMAGE := postgres:18
TEST_DB := aresgate-test-db
TEST_DB_PORT ?= 55432

.DEFAULT_GOAL := help
.PHONY: help up pull down restart rebuild logs ps shell psql backup secret-key rotate-secret-key two-factor-off \
	dev dev-down dev-logs dev-api dev-web install test test-backend test-frontend \
	e2e e2e-up e2e-down e2e-host e2e-coverage e2e-ui e2e-codegen e2e-report e2e-logs \
	lint lint-backend lint-frontend lint-infra format audit scan scan-source scan-image clean

help: ## Show this help
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_-]+:.*## / {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

## ---- Run -----------------------------------------------------------------------
up: ## Build and start AresGate in the background
	$(COMPOSE) up -d --build || { echo; echo "The build failed. Trying once more with the whole log, saved to build.log. The steps that finished are kept."; set -o pipefail; $(COMPOSE) --progress=plain up -d --build 2>&1 | tee build.log; }
	@echo "AresGate is starting at https://$${ARESGATE_SERVER_NAME:-localhost}"

pull: ## Download and start the release in .env's ARESGATE_IMAGE and ARESGATE_VERSION
	$(COMPOSE) pull
	$(COMPOSE) up -d --no-build
	@echo "AresGate is starting at https://$${ARESGATE_SERVER_NAME:-localhost}"

down: ## Stop AresGate (your data is kept)
	$(COMPOSE) down

restart: ## Restart AresGate, e.g. after renewing certificates
	$(COMPOSE) restart

rebuild: ## Rebuild the image from scratch and restart
	$(COMPOSE) build --pull --no-cache
	$(COMPOSE) up -d --force-recreate

logs: ## Follow the logs
	$(COMPOSE) logs -f

ps: ## Show container status and health
	$(COMPOSE) ps

shell: ## Open a shell in the running container
	$(COMPOSE) exec aresgate sh

psql: ## Open a database shell
	$(COMPOSE) exec -u aresgate aresgate psql -h /run/postgresql aresgate

backup: ## Dump the database to ./backups
	@mkdir -p backups
	$(COMPOSE) exec -T -u aresgate aresgate pg_dump -h /run/postgresql -Fc aresgate \
		> backups/aresgate-$$(date +%Y%m%d-%H%M%S).dump
	@ls -1t backups | head -1

two-factor-off: ## Turn off an account's authenticator app (ACCOUNT=<username>)
	@test -n "$(ACCOUNT)" || { echo "Say whose: make two-factor-off ACCOUNT=<username>" >&2; exit 2; }
	$(COMPOSE) exec -T -u aresgate -w /app/backend aresgate python -m app.cli disable-two-factor "$(ACCOUNT)"

secret-key: ## Print the app secret key, to keep somewhere safe apart from the backups
	@$(COMPOSE) exec -u aresgate aresgate cat /data/secrets/secret.key

rotate-secret-key: ## Change the app secret key and seal everything AresGate stores again with it
	$(COMPOSE) exec -T -u aresgate -w /app/backend aresgate python -m app.cli rotate-secret-key

## ---- Develop -------------------------------------------------------------------
dev: ## Run the dev container with live reload (Vite + API)
	$(DEV_COMPOSE) up --build

dev-down: ## Stop the dev container
	$(DEV_COMPOSE) down

dev-logs: ## Follow the dev container's logs
	$(DEV_COMPOSE) logs -f

dev-api: ## Run the API with live reload on http://127.0.0.1:8000 (needs ARESGATE_DATABASE_URL)
	$(BACKEND) ARESGATE_SECRET_KEY="$${ARESGATE_SECRET_KEY:-$$(openssl rand -base64 32)}" \
		uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

dev-web: ## Run the web app with live reload on http://127.0.0.1:5173, proxying /api to the API
	$(FRONTEND) npm run dev

install: ## Install backend and frontend dependencies locally
	$(BACKEND) uv sync
	$(FRONTEND) npm ci --ignore-scripts && npm run e2e:install

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

## ---- End-to-end tests (frontend/e2e/README.md) ---------------------------------
e2e: e2e-up ## Run the Playwright tests against the test container, e.g. make e2e ARGS="home --project=desktop"
	$(FRONTEND) npm run e2e -- $(ARGS)

e2e-up: ## Build and start the test container at https://localhost:9443, with the baseline data
	$(E2E_COMPOSE) up --detach --build --wait --wait-timeout 180
	@curl --silent --show-error --fail --insecure --request POST \
		"https://localhost:$(E2E_PORT)/api/__test__/database/clean" >/dev/null
	@echo "The test server is at https://localhost:$(E2E_PORT) (make e2e-down stops it)"

e2e-down: ## Stop the test container and throw its data away
	$(E2E_COMPOSE) down --volumes

e2e-host: ## Run the Playwright tests with no container: the API and web app run on this computer
	@docker rm --force $(TEST_DB) >/dev/null 2>&1 || true
	docker run --detach --rm --name $(TEST_DB) --publish 127.0.0.1:$(TEST_DB_PORT):5432 \
		--env POSTGRES_USER=aresgate --env POSTGRES_HOST_AUTH_METHOD=trust $(TEST_DB_IMAGE) >/dev/null
	@for _ in $$(seq 60); do \
		docker exec $(TEST_DB) pg_isready --quiet -h 127.0.0.1 -U aresgate && break; sleep 1; \
	done
	@ARESGATE_DATABASE_URL=postgresql+psycopg://aresgate@127.0.0.1:$(TEST_DB_PORT)/aresgate \
		.github/scripts/e2e-host.sh $(ARGS); status=$$?; docker rm --force $(TEST_DB) >/dev/null; exit $$status

e2e-coverage: ## Check the last full run's web coverage reached the minimum (95%)
	$(FRONTEND) npm run e2e:coverage

e2e-ui: e2e-up ## Open Playwright's UI to run and debug tests step by step
	$(FRONTEND) npm run e2e:ui

e2e-codegen: e2e-up ## Record a test by clicking through the app (Playwright's codegen)
	$(FRONTEND) npm run e2e:codegen

e2e-report: ## Open the last run's HTML report
	$(FRONTEND) npm run e2e:report

e2e-logs: ## Follow the test container's logs
	$(E2E_COMPOSE) logs -f

## ---- Check ---------------------------------------------------------------------
lint: lint-backend lint-frontend lint-infra ## Run every linter and type checker

lint-backend: ## ruff, pyright and bandit (API and container scripts)
	$(BACKEND) uv run ruff check . ../docker && uv run ruff format --check . ../docker \
		&& uv run pyright && uv run bandit -c pyproject.toml -r app e2e migrations ../docker -q

lint-frontend: ## ESLint, Prettier and vue-tsc
	$(FRONTEND) npm run lint -- --max-warnings=0 && npm run format:check && npm run typecheck

lint-infra: ## hadolint, ShellCheck and actionlint (Dockerfile, scripts, CI workflows)
	docker run --rm -v "$(CURDIR):/work:ro" -w /work $(HADOLINT_IMAGE) hadolint Dockerfile
	docker run --rm -v "$(CURDIR):/mnt:ro" $(SHELLCHECK_IMAGE) docker/entrypoint.sh docker/start-api.sh \
		docker/apk-retry.sh docker/e2e/start-api.sh .github/scripts/smoke-test.sh \
		.github/scripts/e2e-host.sh .github/scripts/trivy-report.sh \
		.github/scripts/codeql-report.sh .github/scripts/release-version.sh \
		.github/scripts/supplied-key-test.sh .github/scripts/sign-in-test.sh
	docker run --rm -v "$(CURDIR):/repo:ro" -w /repo $(ACTIONLINT_IMAGE) -color

format: ## Auto-format backend and frontend code
	$(BACKEND) uv run ruff check --fix . ../docker && uv run ruff format . ../docker
	$(FRONTEND) npm run lint -- --fix && npm run format

audit: ## Check dependencies for known vulnerabilities (the frontend fails on critical, as CI does)
	$(BACKEND) uv run pip-audit
	$(FRONTEND) npm audit --audit-level=critical

scan: scan-source scan-image ## Scan the code and the built image with Trivy

scan-source: ## Trivy: vulnerable dependencies, leaked secrets and Dockerfile mistakes
	$(TRIVY) -v "$(CURDIR):/src:ro" -w /src $(TRIVY_IMAGE) fs $(TRIVY_FLAGS) \
		--scanners vuln,secret,misconfig --ignorefile .trivyignore.yaml .

scan-image: ## Trivy: vulnerabilities in the built image's packages
	$(TRIVY) -v /var/run/docker.sock:/var/run/docker.sock:ro $(TRIVY_IMAGE) image $(TRIVY_FLAGS) \
		$${ARESGATE_IMAGE:-aresgate}:$${ARESGATE_VERSION:-latest}

clean: ## Remove local build and test artifacts
	rm -rf backend/.pytest_cache backend/.ruff_cache backend/.coverage \
		backend/coverage.xml frontend/dist frontend/coverage frontend/e2e-results build.log
