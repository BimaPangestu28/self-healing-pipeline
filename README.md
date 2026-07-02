# Self-Healing Pipeline

Automated **detect → classify → fix → validate → report** loop for Kubernetes workloads,
with run summaries delivered to **Microsoft Teams as Adaptive Cards**.

This is the Claude Code / Kubernetes reimagining of the OpenClaw "Self-Healing Pipeline"
QA workflow, focused on healing deployment regressions on a cluster. It reuses the
multi-agent SRE modules (`src/agents`, `src/tools`, `src/orchestration`, …) from the
original AIOps SRE agent as a base, and adds two new packages:

- `src/self_healing/` — the pipeline (kube client, coverage matrix, L1 tests, L2 fix, orchestrator)
- `src/notifications/` — Microsoft Teams Adaptive Card builders + delivery client

## How it works

| Phase | What it does | Module |
|-------|--------------|--------|
| 1 — L1 test | Probe deployment readiness + service endpoints | `self_healing/l1_tests.py` |
| 2 — Classify | Match the failure signal to the coverage matrix (runbook) | `self_healing/runbook.py` |
| 3 — L2 fix | Apply the runbook remediation (reset image / restart rollout) | `self_healing/l2_fix.py` |
| 5 — Validation | Re-run L1 to confirm the fix | `self_healing/orchestrator.py` |
| 7 — Report | Render an Adaptive Card and post it to Teams | `notifications/` |

The coverage matrix maps a **failure signal** to a **runbook** with a confidence tier
(`autoFixable`, `guidedInvestigate`, `escalate`, …). Unknown signals escalate instead of
guessing. Only two mutating kube actions are ever taken — `set image` and `rollout restart` —
so the blast radius is auditable.

## Quick start (local cluster)

Prerequisites: `kubectl`, and a local cluster. This was validated on **colima** (k3s):

```bash
colima start --kubernetes --cpu 2 --memory 4 --vm-type vz
```

Set up a light virtualenv (the pipeline itself only needs pydantic + httpx):

```bash
uv venv .venv
uv pip install --python .venv/bin/python pydantic pydantic-settings "httpx<1.0" pytest pytest-asyncio
```

Run the demo. The sample app is deployed with a **deliberately broken image tag**
(`traefik/whoami:v9.9.9-broken-drift`) so the pipeline has something to heal:

```bash
export PYTHONPATH=$PWD
.venv/bin/python run_pipeline.py setup    # deploy the broken app
.venv/bin/python run_pipeline.py status   # healthy: False (ErrImagePull, 0 endpoints)
.venv/bin/python run_pipeline.py run      # detect -> fix -> validate -> print Adaptive Card
.venv/bin/python run_pipeline.py status   # healthy: True (reset to traefik/whoami:v1.10.1)
```

Expected `run` phase log:

```
Phase 1 (L1): 1 failure(s) detected
Phase 2 (Classify): F001 -> autoFixable (RB-INFRA-001)
Phase 3 (L2): F001 FIXED — Set image -> traefik/whoami:v1.10.1; rollout succeeded
Phase 5 (Validation): 0 failure(s) remain
```

`run` exits `0` when the run ends clean (`all_clear`), non-zero otherwise — so CI/cron can gate on it.

## Microsoft Teams delivery

Delivery targets a Teams incoming webhook (Power Automate "Workflows" webhook or a classic
Office 365 connector). Set the URL and the pipeline posts the rendered Adaptive Card:

```bash
export TEAMS_WEBHOOK_URL="https://…/workflows/…"   # from your Teams flow
.venv/bin/python run_pipeline.py run
# -> Teams delivery: sent
```

The payload is a Teams message envelope wrapping an `application/vnd.microsoft.card.adaptive`
attachment (schema 1.4). When `TEAMS_WEBHOOK_URL` is unset, delivery is skipped gracefully and
the card JSON is still printed.

There is also a delivery endpoint for an external orchestrator (cron/agent) to POST a structured
run summary and have this service render + deliver it: `POST /api/v1/pipeline/report`.

## Tests

```bash
PYTHONPATH=$PWD .venv/bin/python -m pytest tests/test_self_healing.py tests/test_teams_notifications.py -q
```

`test_self_healing.py` exercises the full detect→fix→validate loop against an in-memory fake
cluster (no kubectl needed); `test_teams_notifications.py` covers the Adaptive Card builders and
the real HTTP delivery path.

## Commands reference

| Command | Purpose |
|---------|---------|
| `run_pipeline.py setup` | Apply the sample workload manifest (`deploy/sample-app.yaml`) |
| `run_pipeline.py break` | Re-introduce the bug (set the broken image) |
| `run_pipeline.py status` | Print current image, availability, endpoints |
| `run_pipeline.py run` | Execute the pipeline and print/deliver the report |
