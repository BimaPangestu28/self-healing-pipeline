# Self-Healing Pipeline — developer & demo shortcuts.
#
# Quick start:
#   make install cluster-up   # one-time setup
#   make demo                 # open http://127.0.0.1:8080
#   make test test-e2e        # unit + end-to-end tests

VENV       := .venv
PY         := $(VENV)/bin/python
PIP        := uv pip install --python $(PY)
RUN_DEPS   := pydantic pydantic-settings "httpx<1.0" fastapi "uvicorn[standard]"
TEST_DEPS  := pytest pytest-asyncio

# Make kubectl and the venv visible to every recipe, and put src on the path.
export PYTHONPATH := $(CURDIR)
export PATH := /usr/local/bin:$(CURDIR)/.venv/bin:$(PATH)

.DEFAULT_GOAL := help
.PHONY: help install install-ansible install-playwright \
        cluster-up cluster-down cluster-status \
        demo demo-ansible pipeline-setup pipeline-run pipeline-status pipeline-break \
        test test-e2e test-all screenshots clean

help: ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# --- setup ----------------------------------------------------------------

install: ## Create the venv and install run + test dependencies
	uv venv $(VENV)
	$(PIP) $(RUN_DEPS) $(TEST_DEPS)

install-ansible: ## Install ansible-core (for EXECUTOR=ansible)
	$(PIP) ansible-core

install-playwright: ## Install Playwright + Chromium (for screenshots)
	$(PIP) playwright
	$(PY) -m playwright install chromium

# --- local cluster (colima / k3s) -----------------------------------------

cluster-up: ## Start a local k3s cluster via colima
	colima start --kubernetes --cpu 2 --memory 4 --vm-type vz

cluster-down: ## Stop the colima cluster
	colima stop

cluster-status: ## Show nodes and the sample-app pods
	kubectl get nodes
	kubectl -n self-healing get pods -l app=sample-app || true

# --- interactive approval demo --------------------------------------------

demo: ## Run the interactive approval demo (Kubernetes executor) at :8080
	$(PY) run_demo.py

demo-ansible: install-ansible ## Run the demo with the real Ansible executor
	EXECUTOR=ansible $(PY) run_demo.py

# --- self-healing pipeline CLI --------------------------------------------

pipeline-setup: ## Deploy the sample app with the broken image (on purpose)
	$(PY) run_pipeline.py setup

pipeline-run: ## Run the pipeline (detect -> fix -> validate -> report)
	$(PY) run_pipeline.py run

pipeline-status: ## Show current app image / availability / endpoints
	$(PY) run_pipeline.py status

pipeline-break: ## Re-introduce the broken image
	$(PY) run_pipeline.py break

# --- tests ----------------------------------------------------------------

test: ## Run unit tests (fakes, no cluster needed)
	$(PY) -m pytest \
		tests/test_self_healing.py \
		tests/test_teams_notifications.py \
		tests/test_approvals.py \
		tests/test_teams_endpoint.py -q

test-e2e: ## Run end-to-end integration tests against the real cluster
	$(PY) -m pytest tests/test_integration_e2e.py -v

test-all: test test-e2e ## Run unit + end-to-end tests

# --- misc -----------------------------------------------------------------

screenshots: install-playwright ## Capture demo UI screenshots into docs/screenshots
	$(PY) scripts/screenshots.py

clean: ## Remove the venv and Python caches
	rm -rf $(VENV)
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name '.pytest_cache' -prune -exec rm -rf {} +
