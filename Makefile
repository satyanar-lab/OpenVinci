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

.PHONY: help install install-backend install-frontend dev test test-backend test-frontend clean

help:
	@echo "OpenVinci — make targets"
	@echo "  make install    install backend (Python venv) and frontend (npm) deps"
	@echo "  make dev        run backend + frontend in one process group (Ctrl+C kills both)"
	@echo "  make test       run pytest and vitest"
	@echo "  make clean      remove .venv and node_modules"

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

test-backend:
	cd $(BACKEND) && $(PYENV) $(PYTEST)

test-frontend:
	cd $(FRONTEND) && npm test

clean:
	rm -rf $(VENV) $(FRONTEND)/node_modules
