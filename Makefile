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

.PHONY: help check-submodule install install-backend install-frontend dev build run desktop desktop-app test test-backend test-frontend test-functional test-golden verify clean

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
	@echo "  make dev             run backend + frontend separately (Vite on :5173, FastAPI on :8000)"
	@echo "  make build           produce the production frontend bundle in frontend/dist"
	@echo "  make run             build + serve everything on http://127.0.0.1:8000 (single process)"
	@echo "  make desktop         build + launch as a desktop app (pywebview window)"
	@echo "  make desktop-app     bundle into a single double-click artifact (PyInstaller)"
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

# Build the production frontend bundle. `frontend/dist/` is where the
# backend's SPA catch-all looks (FRONTEND_DIST in app/main.py).
build:
	cd $(FRONTEND) && npm run build

# Single-process serve: build the SPA, then start uvicorn — same port,
# same origin, no second dev server. Useful for previewing what
# end-users see and for any future deploy story.
run: build
	$(PYENV) $(UVICORN) --app-dir $(BACKEND) app.main:app --host $(BACKEND_HOST) --port $(BACKEND_PORT)

# Desktop launcher: build the SPA, then open a pywebview native window
# pointing at uvicorn on a free port. Requires `pip install -e
# backend[desktop]` so pywebview is available — see README "Run as a
# desktop app".
desktop: build
	$(PYENV) $(PY) -m desktop.app

# Single double-click artifact via PyInstaller. Builds the SPA first
# so the dist/ tree is current, then bakes the launcher + the backend
# + vendor/as/{tools,infras} + frontend/dist + examples + model into
# one OS-native binary at dist/OpenVinci. PER-OS BUILD: run this on
# the target platform you want to ship for (cross-compiling Python
# bundles is not a thing). See README "Build a double-click bundle".
desktop-app: build
	@$(PYENV) $(PY) -c "import PyInstaller" 2>/dev/null \
		|| { echo "==> installing pyinstaller into the backend venv"; \
		     $(PIP) install --quiet "pyinstaller>=6"; }
	@$(PYENV) $(PY) -c "import webview" 2>/dev/null \
		|| { echo "==> installing pywebview into the backend venv"; \
		     $(PIP) install --quiet "pywebview>=5"; }
	$(PYENV) $(VENV)/bin/pyinstaller --noconfirm --clean desktop.spec
	@echo ""
	@echo "Bundle written to: $(ROOT)/dist/OpenVinci"
	@echo "Run it: ./dist/OpenVinci          (windowed)"
	@echo "        ./dist/OpenVinci --no-window   (headless smoke-test)"

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
