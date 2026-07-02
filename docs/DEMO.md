# Technical Demo Runbook

A script for showing the system to a **technical audience** — not just the UI, but
the real operations underneath (kubectl, cgroup, LLM tool calls, API, CLI).

## Terminal layout (3 panes)

```
┌───────────────────────────┬───────────────────────────┐
│ Pane A: the demo server    │ Pane B: watch the cluster  │
│   make demo                │   watch -n1 kubectl -n \    │
│   (logs stream here)       │     self-healing get pods  │
├───────────────────────────┴───────────────────────────┤
│ Pane C: ad-hoc kubectl / curl (prove it's real)         │
└─────────────────────────────────────────────────────────┘
```

Browser: **http://127.0.0.1:8080** (UI) and **http://127.0.0.1:8080/docs** (API).

## 0. Setup (once)

```bash
make install cluster-up          # venv + local cluster
export LLM_PROVIDER=deepseek DEEPSEEK_API_KEY=sk-...   # optional: real LLM analysis
make demo                        # builds image, serves UI at :8080
```

## 1. Human-approved remediation (with live cluster proof)

- Pane B: `watch -n1 kubectl -n self-healing get pods -l app=memory-app`
- Browser UI → **▶ Start scenario**. Show the healthcheck card: **real** node/pod/IP
  and **real** memory % (read from the pod cgroup, not hardcoded).
- Click **Approve**. In Pane B, the pod is replaced (real `rollout restart`); the
  result card flips to **OK Healthy** with memory back to baseline.
- Talking point: memory % comes from `/sys/fs/cgroup/memory.current ÷ memory.max`.

## 2. Autonomous remediation (AIOps, no human)

- Browser UI → **⚡ Auto-heal**. Same detect→fix→verify, but **no approval** — the
  runbook tier `autoFixable` auto-executes. Pane B shows the restart.
- Talking point: policy — autonomous for high-confidence/low-risk, approval for risky.

## 3. Conversational agent (LLM tool-calling)

- In the chat box type: `how is outsystem?` → the LLM calls `get_healthcheck` and
  returns a card + summary. Then `please fix the memory issue` → it calls
  `propose_remediation`, which opens an approval card. It **cannot execute** — only
  a human Approve (or the autonomous policy) runs it.

## 4. Under the hood — live activity (the money shot for technical folks)

- Bottom panel **⚙️ Under the hood** streams the real operations as you click:
  `kubectl get/exec`, cgroup reads, `rollout restart`, LLM tool calls.
- Or hit it directly:
  ```bash
  curl -s 'http://127.0.0.1:8080/api/demo/logs?after=0' | jq '.entries[] | "\(.level) \(.logger): \(.message)"'
  ```

## 5. API explorer (Swagger) + curl

- Open **http://127.0.0.1:8080/docs** — every endpoint is documented and runnable.
- Or drive it headless:
  ```bash
  curl -s -X POST :8080/api/demo/healthcheck | jq .healthy,.memory_percent
  curl -s -X POST :8080/api/demo/autonomous  | jq .note
  ```

## 6. Prove the metric is real (not simulated)

```bash
POD=$(kubectl -n self-healing get pod -l app=memory-app -o jsonpath='{.items[0].metadata.name}')
kubectl -n self-healing exec "$POD" -- sh -c 'echo used=$(cat /sys/fs/cgroup/memory.current) limit=$(cat /sys/fs/cgroup/memory.max)'
# The demo's memory % is used ÷ limit from exactly these numbers.
```

## 7. Autonomous CLI pipeline (image-drift scenario)

```bash
make pipeline-setup     # deploy a deployment with a broken image tag
make pipeline-run       # detect drift → classify → reset image → validate (no approval)
make pipeline-status
```

## Talking points: what's real vs. staged

- **Real:** the cluster, pod readiness, memory metric (cgroup), the remediation
  (rollout restart / ansible-playbook), identity (node/pod/IP), the LLM analysis,
  the Teams Adaptive Card contract + Bot Framework JWT auth.
- **Staged for the demo:** the memory pressure is induced on purpose (`/leak`), and
  the branding ("AION"). Everything operational is real.
- See `docs/USE_CASES.md` for the full matrix and `docs/ARCHITECTURE.md` for internals.
