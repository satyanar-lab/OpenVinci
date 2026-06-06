SHELL := /usr/bin/env bash

ROOT       := $(CURDIR)
BACKEND    := $(ROOT)/backend
FRONTEND   := $(ROOT)/frontend
VENV       := $(BACKEND)/.venv
PY         := $(VENV)/bin/python
PIP        := $(VENV)/bin/pip
UVICORN    := $(VENV)/bin/uvicorn
PYTEST     := $(VENV)/bin/pytest

# Strip inherited PYTHONPATH so a system Python (e.g. ROS at /opt/ros/...)
# doesn't leak unrelated pytest plugins into our venv.
PYENV := PYTHONPATH= PYTHONNOUSERSITE=1

BACKEND_HOST ?= 127.0.0.1
BACKEND_PORT ?= 8000

.PHONY: help check-submodule install install-backend install-frontend dev test test-backend test-frontend test-functional test-golden verify clean

# Hard guard for every target that needs vendor/as. A fresh clone without
# the submodule used to let L1-gen / L2 / L3 silently skip or fail in
# obscure ways. Now: clear error, exit non-zero, never silent-pass.
check-submodule:
	@test -d $(ROOT)/vendor/as/infras || { \
		echo "" >&2; \
		echo "ERROR: vendor/as submodule is not initialized." >&2; \
		echo "" >&2; \
		echo "Run: git submodule update --init --recursive" >&2; \
		echo "" >&2; \
		exit 2; \
	}

help:
	@echo "OpenVinci — make targets"
	@echo "  make install         install backend (Python venv) and frontend (npm) deps"
	@echo "  make dev             run backend + frontend in one process group (Ctrl+C kills both)"
	@echo "  make test            run pytest and vitest (unit tests)"
	@echo "  make test-functional run the L2 functional loopback (slow, needs gcc)"
	@echo "  make test-golden     run the L3 golden-file regression"
	@echo "  make verify          run the full verification report (all levels)"
	@echo "  make clean           remove .venv, node_modules, and build/ artifacts"

install: install-backend install-frontend

install-backend:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e "$(BACKEND)[dev]"

install-frontend:
	cd $(FRONTEND) && npm install

dev:
	@trap 'kill 0' EXIT INT TERM; \
	$(PYENV) $(UVICORN) --app-dir $(BACKEND) app.main:app --host $(BACKEND_HOST) --port $(BACKEND_PORT) --reload & \
	cd $(FRONTEND) && npm run dev -- --host 127.0.0.1 & \
	wait

test: test-backend test-frontend

test-functional: check-submodule
	OPENVINCI_RUN_FUNCTIONAL=1 $(PYENV) $(PYTEST) $(ROOT)/tests/functional -v

test-golden: check-submodule
	$(PYENV) $(PYTEST) $(ROOT)/tests/golden -v

verify: check-submodule
	$(ROOT)/scripts/verify.sh

# Most backend tests work without vendor/as (round-trip, schema,
# engine rules); the gen / DBC-matrix subsets don't. Guard the full
# suite to keep failure messages clear.
test-backend: check-submodule
	cd $(BACKEND) && $(PYENV) $(PYTEST)

test-frontend:
	cd $(FRONTEND) && npm test

clean:
	rm -rf $(VENV) $(FRONTEND)/node_modules $(ROOT)/build
