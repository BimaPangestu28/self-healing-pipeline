# Architecture

Two entry points share the same domain: an **autonomous CLI pipeline** (image-drift
self-healing) and an **approval/agent demo server** (memory scenario, Teams-style).
Both act on a real Kubernetes cluster; the LLM is advisory only.

## Components

```mermaid
flowchart TB
    subgraph Clients
      UI["Web UI (Adaptive Cards)"]
      Teams["MS Teams / Bot"]
      CLI["run_pipeline.py / Makefile"]
    end

    subgraph API["FastAPI (demo/app.py)"]
      EP["/api/demo/* , /api/teams/messages, /api/demo/logs, /docs"]
      TRACE["Activity log (ring buffer)"]
    end

    subgraph Domain["src/approvals"]
      SVC["DemoService\nhealthcheck · recommend · approve · autonomous"]
      AGENT["ChatAgent\n(LLM tool-calling)"]
      EXalso["Executors\nKubernetes | Ansible | AWX"]
      CARDS["Adaptive Card builders"]
      BOTAUTH["bot_auth (JWT)"]
    end

    subgraph Heal["src/self_healing"]
      PIPE["SelfHealingPipeline"]
      L1["l1_tests"]
      RB["runbook (coverage matrix)"]
      L2["l2_fix"]
      KUBE["KubeClient → kubectl"]
    end

    LLM["LLM: DeepSeek / Azure OpenAI"]
    K8S["Kubernetes cluster\n(memory-app / sample-app)"]
    NOTIF["src/notifications\nTeams incoming webhook"]

    UI --> EP
    Teams --> EP
    CLI --> PIPE
    EP --> SVC
    EP --> AGENT
    EP --> BOTAUTH
    AGENT --> LLM
    SVC --> AGENT
    SVC --> EXalso
    SVC --> CARDS
    SVC --> KUBE
    EXalso --> KUBE
    PIPE --> L1 --> KUBE
    PIPE --> RB
    PIPE --> L2 --> KUBE
    KUBE --> K8S
    SVC -. analysis .-> LLM
    EP --> TRACE
    SVC -. report .-> NOTIF --> Teams
```

## Request flow — approval demo

1. **Detect** — `DemoService.healthcheck()` reads real readiness (deployment/endpoints)
   and real memory (`KubeClient.pod_memory_percent` → pod cgroup), plus identity
   (`pod_identity` → node/pod/IP).
2. **Analyze** — `analysis.build_analysis()` asks the LLM (or templates) for a
   root-cause + recommendation narrative.
3. **Recommend** — `recommend_action()` builds an `ActionSpec` with **cluster-derived**
   parameters (namespace/deployment/pod/node), or AWX params under the AWX executor.
4. **Decide** —
   - *Approval mode:* `create_approval()` → interactive Adaptive Card; a human clicks
     Approve/Reject (web `Action.Execute`, or Teams invoke → `/api/teams/messages`).
   - *Autonomous mode:* `autonomous_remediate()` executes immediately for `autoFixable`.
5. **Execute** — the selected `Executor` performs the real remediation
   (`KubernetesExecutor` = `kubectl rollout restart`; `AnsibleExecutor` = a real
   `ansible-playbook`; `AwxExecutor` = launch + poll an AWX job).
6. **Verify** — a fresh healthcheck confirms healthy; a completion card is returned.

## Request flow — autonomous pipeline (image drift)

`SelfHealingPipeline.run()`: `l1_tests` (readiness/drift) → `runbook.classify`
(coverage matrix → tier) → `l2_fix` (reset image / rollout restart) → validation.
No human in the loop; exits non-zero if unresolved (CI/cron-friendly).

## Trust boundaries / auth

- **Teams inbound** (`/api/teams/messages`): Bot Framework **JWT** when
  `MICROSOFT_APP_ID` is set; otherwise HMAC (outgoing webhook) or open (dev).
- **Remediation is gated**: the LLM can only *propose*; execution needs approval or
  the autonomous policy. Only two mutating kube verbs are used (set image, rollout
  restart).

## Observability

`demo/trace.py` attaches a ring-buffer log handler to the `src`/`demo` loggers;
`GET /api/demo/logs` and the UI "Under the hood" panel stream the real operations
(kubectl commands, cgroup reads, executor actions, LLM tool calls).

## What's real vs staged

Real: cluster, readiness, memory metric (cgroup), remediation, identity, LLM
analysis, Teams card contract + JWT. Staged: induced memory pressure (`/leak`) and
branding. See `docs/USE_CASES.md`.
