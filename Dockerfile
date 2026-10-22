# syntax=docker/dockerfile:1

# AresGate ships as one container: nginx (TLS), the FastAPI app, Postgres and the built
# Vue frontend, run by supervisord. Every stage builds on Chainguard's Wolfi, whose
# packages are rebuilt as soon as CVE fixes land, and the build stages keep Node, uv and
# compilers out of the final image.

# Chainguard's free tier only publishes wolfi-base as :latest, so builds pin the digest that
# :latest had when this line was last updated, to stay reproducible. `apk upgrade` below still
# pulls the newest package fixes.
ARG WOLFI_BASE=cgr.dev/chainguard/wolfi-base@sha256:fac38d12efdb4bf43ac9e599a31db10a27ad5dd71e5f1618790962eda8d66180
ARG PYTHON_VERSION=3.14
ARG NODE_VERSION=24
ARG POSTGRES_VERSION=18
ARG UV_VERSION=0.13.3
ARG SUPERVISOR_VERSION=4.3.0

# Every apk call goes through docker/apk-retry.sh: a package download that stalls on a CI
# runner fails the whole build otherwise, and the script runs the call again. It's mounted
# for just the steps that use it, so it never ends up in an image layer.

# ---- Wolfi base, upgraded to the latest packages ----------------------------------------
FROM ${WOLFI_BASE} AS wolfi
# CI passes the date here so cached layers are refreshed at least daily.
ARG APK_REFRESH=""
RUN --mount=type=bind,source=docker/apk-retry.sh,target=/apk-retry.sh \
    echo "apk refresh: ${APK_REFRESH:-none}" && sh /apk-retry.sh apk upgrade --no-cache

# ---- Frontend: type-check and build static assets ------------------------------------
# The web app is the same on every CPU, so a multi-platform release builds it once, natively
# on the build machine, instead of under emulation for each platform.
FROM --platform=$BUILDPLATFORM ${WOLFI_BASE} AS frontend-build
ARG NODE_VERSION
ARG APK_REFRESH=""
RUN --mount=type=bind,source=docker/apk-retry.sh,target=/apk-retry.sh \
    echo "apk refresh: ${APK_REFRESH:-none}" && sh /apk-retry.sh apk upgrade --no-cache \
    && sh /apk-retry.sh apk add --no-cache "nodejs-${NODE_VERSION}" npm
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
# npm tries a failed download twice by default; a slow connection needs more.
ENV NPM_CONFIG_FETCH_RETRIES=5
# No package's install scripts run (none of these need one), and the Python stages below
# install prebuilt wheels only, so installing dependencies never runs their code.
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- uv binary ------------------------------------------------------------------------
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

# ---- Backend: resolve the locked Python environment -----------------------------------
FROM wolfi AS backend-build
ARG PYTHON_VERSION
ARG SUPERVISOR_VERSION
RUN --mount=type=bind,source=docker/apk-retry.sh,target=/apk-retry.sh \
    sh /apk-retry.sh apk add --no-cache "python-${PYTHON_VERSION}"
COPY --from=uv /uv /usr/local/bin/uv
# uv gives up on a download that stalls for 30 seconds, which a slow connection does when the
# image's layers download at once, so it waits longer and tries more often.
ENV UV_COMPILE_BYTECODE=1 \
    UV_HTTP_RETRIES=5 \
    UV_HTTP_TIMEOUT=300 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON=/usr/bin/python${PYTHON_VERSION} \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-build
# supervisord gets its own environment so it never shares dependencies with the app.
RUN uv venv /opt/supervisor \
    && uv pip install --no-build --python /opt/supervisor/bin/python \
        "supervisor==${SUPERVISOR_VERSION}"

# ---- Runtime base: Postgres, nginx mainline and Python from Wolfi ----------------------
FROM wolfi AS runtime-base
ARG PYTHON_VERSION
ARG POSTGRES_VERSION
# CI passes a value that changes on every run, so the packages that ship in the image are
# upgraded when the image is built, even when the base stage above comes from the cache.
ARG IMAGE_REFRESH=""
# Wolfi packages don't create service accounts, so they're made here with fixed IDs that
# stay the same across rebuilds (the database files on the volume belong to postgres).
RUN --mount=type=bind,source=docker/apk-retry.sh,target=/apk-retry.sh \
    set -eux; \
    echo "image refresh: ${IMAGE_REFRESH:-none}"; \
    addgroup -S -g 10001 aresgate; \
    adduser -S -D -H -u 10001 -G aresgate -h /app -s /sbin/nologin aresgate; \
    addgroup -S -g 10002 postgres; \
    adduser -S -D -H -u 10002 -G postgres -h /var/lib/postgresql -s /sbin/nologin postgres; \
    addgroup -S -g 10003 nginx; \
    adduser -S -D -H -u 10003 -G nginx -h /var/lib/nginx -s /sbin/nologin nginx; \
    sh /apk-retry.sh apk add --no-cache --upgrade ca-certificates-bundle nginx-mainline \
        nginx-mainline-config openssl setpriv tzdata; \
    sh /apk-retry.sh apk add --no-cache --upgrade "postgresql-${POSTGRES_VERSION}" \
        "postgresql-${POSTGRES_VERSION}-client" "python-${PYTHON_VERSION}"; \
    sh /apk-retry.sh apk upgrade --no-cache; \
    rm -f /etc/nginx/conf.d/default.conf
ENV PATH=/opt/venv/bin:/opt/supervisor/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
COPY --from=backend-build /opt/venv /opt/venv
COPY --from=backend-build /opt/supervisor /opt/supervisor
COPY docker/nginx/nginx.conf /etc/nginx/nginx.conf
COPY docker/nginx/templates /etc/nginx/aresgate-templates
COPY docker/supervisor/supervisord.conf /etc/supervisor/supervisord.conf
COPY docker/supervisor/conf.d /etc/supervisor/conf.d
COPY --chmod=0755 docker/entrypoint.sh docker/start-api.sh docker/render-nginx-config.py \
    docker/healthcheck.py docker/exit-on-fatal.py /app/docker/
COPY backend/alembic.ini /app/backend/alembic.ini
COPY backend/migrations /app/backend/migrations
COPY backend/app /app/backend/app
VOLUME ["/data"]
EXPOSE 8080 8443
# Checks the whole path (nginx, TLS, API, database), not just the API process.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD ["python", "/app/docker/healthcheck.py"]
ENTRYPOINT ["/app/docker/entrypoint.sh"]

# ---- Development: same container plus Node, dev tools and live reload ------------------
FROM runtime-base AS dev
ARG NODE_VERSION
ARG PYTHON_VERSION
RUN --mount=type=bind,source=docker/apk-retry.sh,target=/apk-retry.sh \
    sh /apk-retry.sh apk add --no-cache "nodejs-${NODE_VERSION}" npm
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_PYTHON=/usr/bin/python${PYTHON_VERSION} \
    UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy UV_HTTP_RETRIES=5 UV_HTTP_TIMEOUT=300 \
    ARESGATE_MODE=development ARESGATE_ENVIRONMENT=development
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-build
WORKDIR /app/frontend
COPY --chown=aresgate:aresgate frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund && chown -R aresgate:aresgate /app/frontend
WORKDIR /app
COPY docker/supervisor/dev.d /etc/supervisor/conf.d

# ---- Production image (default target) ------------------------------------------------
FROM runtime-base AS runtime
# The release workflow passes the release's version (e.g. 1.4.0), which Settings > System
# shows; other builds report the version in backend/app/__init__.py.
ARG RELEASE=""
COPY --from=frontend-build /src/dist /usr/share/aresgate/www
ENV ARESGATE_MODE=production ARESGATE_ENVIRONMENT=production ARESGATE_RELEASE=${RELEASE}
