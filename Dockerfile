# syntax=docker/dockerfile:1.7
#
# OpenVinci — multi-stage build that produces ONE runnable image.
#
# Stage 1 (node)        builds the frontend bundle (Vite / TS).
# Stage 2 (python-slim) installs the BSW toolchain (gcc / make / git),
#                       the FastAPI backend, vendor/as, and the dist
#                       bundle from stage 1. Runs as a non-root user.
#
# The whole point of this image is that the verification toolchain
# travels with the app: the same `scripts/verify.sh` you run locally
# also runs inside the container, against the same vendor/as sources
# (see README "Run the container" for the verify-inside steps).
#
# Build-context prerequisite:
#   git submodule update --init vendor/as
# The image COPYs vendor/as straight from the context — there's no
# `git submodule` at image build time on purpose, so an offline
# build with a vendored tarball works the same way.

# ---------------------------------------------------------------------
# Stage 1: frontend bundle
# ---------------------------------------------------------------------
FROM node:20-alpine AS frontend-builder

WORKDIR /work/frontend

# Install deps from the lock-file first so the layer caches even when
# only TS / CSS sources change.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------------
# Stage 2: backend + runtime
# ---------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# --- OS-level toolchain ----------------------------------------------
# build-essential ⇒ gcc + g++ + libc-dev + make (L1 syntax-check
# subprocess.run on every *_Cfg.c). git is here per the prompt's
# request and is also handy for any in-container submodule fix-up
# during debugging. uuid-dev / libuuid1 cover the L2 functional node
# link (-luuid via the simulator backends — not exercised by L1 but
# kept ready so running `scripts/verify.sh` inside the container is
# a one-step affair).
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        git \
        libuuid1 \
        uuid-dev \
 && rm -rf /var/lib/apt/lists/*

# --- non-root user ---------------------------------------------------
ARG APP_UID=1000
ARG APP_GID=1000
RUN groupadd --system --gid ${APP_GID} openvinci \
 && useradd  --system --uid ${APP_UID} --gid openvinci \
              --home /app --shell /bin/bash openvinci

WORKDIR /app

# --- application sources --------------------------------------------
# Layer order: lightweight first, then backend (so the heavy `pip
# install` layer below only re-runs when pyproject.toml changes), then
# vendor/as last (it's the biggest layer).
COPY model/    model/
COPY examples/ examples/
COPY scripts/  scripts/
COPY tests/    tests/
COPY backend/  backend/

# --- backend Python deps --------------------------------------------
# Editable install picks up fastapi / cantools / scons / pycrc / etc.
# `[dev]` adds pytest + httpx2 + jsonschema so `pytest` and
# `scripts/verify.sh` both run from inside the container.
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -e "/app/backend[dev]"

COPY vendor/as/ vendor/as/

# --- pre-built frontend ---------------------------------------------
COPY --from=frontend-builder /work/frontend/dist frontend/dist

# --- entrypoint + perms ---------------------------------------------
COPY docker/entrypoint.sh /usr/local/bin/openvinci-entrypoint
RUN chmod +x /usr/local/bin/openvinci-entrypoint \
 && chown -R openvinci:openvinci /app

# Strip any inherited PYTHONPATH so a system Python (ROS et al.)
# doesn't leak into the install. Matches the Makefile + verify.sh.
ENV PYTHONPATH="" \
    PYTHONNOUSERSITE=1 \
    PYTHONUNBUFFERED=1 \
    OPENVINCI_FRONTEND_DIST=/app/frontend/dist

USER openvinci

EXPOSE 8000

ENTRYPOINT ["openvinci-entrypoint"]
CMD ["uvicorn", \
     "--app-dir", "/app/backend", \
     "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000"]
