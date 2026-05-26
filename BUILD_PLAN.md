# MCP Server Factory — Build Plan

> A self-service platform for business developers to publish Python functions as enterprise MCP servers, with admin approval workflow and automated Azure provisioning.

---

## 1. Product Vision

### Who It Serves
| Role | Goal |
|------|------|
| **Business Developer** | Upload Python tool functions → get a running, secured MCP server without knowing Docker or Azure |
| **Platform Admin** | Review, approve, and govern all MCP servers before they go live |

### What It Replaces
Manually copying the `mcp-server-boilerplate` template, configuring Azure, writing Dockerfiles, and setting up CI/CD pipelines — all replaced by a guided web UI and automated provisioning pipeline.

---

## 2. System Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Frontend (Next.js 14)                        │
│                                                                      │
│  ┌─────────────────┐  ┌──────────────────┐  ┌───────────────────┐  │
│  │  Code Editor    │  │  Tool Preview    │  │  Admin Dashboard  │  │
│  │  (Monaco)       │  │  (LLM-eye view)  │  │  (Approval Queue) │  │
│  └─────────────────┘  └──────────────────┘  └───────────────────┘  │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ REST + WebSocket
┌──────────────────────────────▼───────────────────────────────────────┐
│                        Backend (FastAPI)                              │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │ Code Parser  │  │ Approval     │  │ Provisioning Pipeline    │  │
│  │ (AST)        │  │ State Machine│  │ (Async Task Queue / ARQ) │  │
│  └──────────────┘  └──────────────┘  └──────────────────────────┘  │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │ Sandbox      │  │ Code Gen     │  │ Azure Provisioner        │  │
│  │ (Docker SDK) │  │ (Templates)  │  │ (azure-mgmt-*)           │  │
│  └──────────────┘  └──────────────┘  └──────────────────────────┘  │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
               ┌───────────────┴────────────────┐
               │         PostgreSQL              │
               │  projects / submissions /       │
               │  approvals / deployments        │
               └────────────────────────────────┘
```

---

## 3. Tech Stack

| Layer | Choice | Reason |
|-------|--------|--------|
| Frontend | Next.js 14 (App Router) + TypeScript | SSR, file-based routing, good DX |
| UI Components | shadcn/ui + Tailwind CSS | Unstyled primitives, rapid composition |
| Code Editor | Monaco Editor (via `@monaco-editor/react`) | Same as VS Code; Python syntax + inline errors |
| Backend | FastAPI (Python 3.12) | Consistent with boilerplate; async-native |
| Task Queue | ARQ (async Redis queue) | Lightweight, async, no Celery overhead |
| Database | PostgreSQL 16 + SQLAlchemy 2 (async) + Alembic | Reliable, relational audit trail |
| Auth | Azure Entra ID (MSAL) + JWT | SSO consistency with provisioned servers |
| Sandbox | Docker SDK (`docker-py`) with `--network=none` | Isolate user code execution |
| Code Generation | Jinja2 templates | Simple, auditable, debuggable |
| Azure SDK | `azure-mgmt-containerinstance`, `azure-mgmt-graphrbac`, `azure-identity` | Programmatic provisioning |
| Container Registry | Azure Container Registry (ACR) | Enterprise-standard |
| Hosting (Platform) | Azure Container Apps | Serverless, scales to zero |
| Notifications | Microsoft Teams Webhook / SendGrid | Enterprise-native alerting |

---

## 4. Database Schema

```sql
-- Users synced from Azure Entra on first login
users (
  id            UUID PK,
  oid           TEXT UNIQUE,   -- Azure object ID
  email         TEXT,
  display_name  TEXT,
  role          ENUM('developer', 'admin'),
  created_at    TIMESTAMPTZ
)

-- A named MCP server project owned by a developer
projects (
  id            UUID PK,
  owner_id      UUID FK → users,
  name          TEXT UNIQUE,
  description   TEXT,
  department    TEXT,
  created_at    TIMESTAMPTZ,
  archived_at   TIMESTAMPTZ
)

-- Each submission is an immutable code snapshot
submissions (
  id            UUID PK,
  project_id    UUID FK → projects,
  submitted_by  UUID FK → users,
  version       INT,
  tools_code    TEXT,          -- raw Python source
  requirements  TEXT,          -- requirements.txt content
  test_code     TEXT,          -- optional pytest file
  status        ENUM('draft','pending','sandbox_running',
                     'sandbox_failed','awaiting_approval',
                     'approved','rejected','provisioning',
                     'deployed','failed'),
  static_report JSONB,         -- Layer 1 results
  sandbox_report JSONB,        -- Layer 2 results
  test_report   JSONB,         -- Layer 3 results
  submitted_at  TIMESTAMPTZ,
  updated_at    TIMESTAMPTZ
)

-- Admin approval decisions
approvals (
  id            UUID PK,
  submission_id UUID FK → submissions,
  reviewer_id   UUID FK → users,
  decision      ENUM('approved','rejected'),
  comment       TEXT,
  decided_at    TIMESTAMPTZ
)

-- Azure resources created per approved submission
deployments (
  id               UUID PK,
  submission_id    UUID FK → submissions,
  mcp_url          TEXT,
  acr_image        TEXT,
  aca_resource_id  TEXT,
  app_reg_client_id TEXT,
  key_vault_id     TEXT,
  deployed_at      TIMESTAMPTZ,
  torn_down_at     TIMESTAMPTZ
)
```

---

## 5. Submission State Machine

```
                     ┌─────────────────────────────────┐
                     │           DRAFT                 │
                     │  (saved, not submitted yet)     │
                     └──────────────┬──────────────────┘
                                    │ developer submits
                                    ▼
                     ┌─────────────────────────────────┐
                     │       SANDBOX_RUNNING            │
                     │  (Layer 1 + 2 + 3 checks)       │
                     └──────────────┬──────────────────┘
                          ┌─────────┴─────────┐
                        fail                pass
                          │                  │
                          ▼                  ▼
                   SANDBOX_FAILED    AWAITING_APPROVAL
                   (back to dev)    (admin notified)
                                         │
                              ┌──────────┴──────────┐
                           reject                approve
                              │                    │
                              ▼                    ▼
                          REJECTED           PROVISIONING
                       (back to dev)       (Azure pipeline)
                                                  │
                                       ┌──────────┴──────────┐
                                     fail                  pass
                                       │                    │
                                       ▼                    ▼
                                    FAILED              DEPLOYED
                                 (alert admin)       (URL issued)
```

---

## 6. Validation Layers

### Layer 1 — Static Analysis (real-time, no execution)
Runs instantly on every keystroke in the editor.

| Check | Method | Severity |
|-------|--------|----------|
| Python syntax valid | `compile()` | Error — blocks submission |
| All params have type annotations | AST walk | Error — blocks submission |
| All tool functions have docstrings | AST walk | Warning |
| No `os.system` / `subprocess` calls | AST walk | Error — blocks submission |
| No hardcoded secrets pattern | Regex | Error — blocks submission |
| `import` statements extracted | AST walk | Info — populates requirements |

### Layer 2 — Sandboxed Dry-Run (triggered on submission)
Runs user code in an isolated Docker container.

```
Container constraints:
  --network=none          # no outbound calls
  --memory=256m
  --cpus=0.5
  --read-only filesystem  # except /tmp
  timeout: 30 seconds

What we test:
  1. pip install requirements succeeds
  2. Module imports without error
  3. Each tool function is callable
  4. Auto-generated inputs (from type hints) don't cause crashes
  5. Return type matches declared annotation
  6. All external calls are auto-mocked (requests, psycopg2, etc.)
```

### Layer 3 — User-Provided Tests (optional, same sandbox)
```
uv run pytest test_tools.py -v --tb=short --timeout=20
```
Results (pass/fail/coverage) are shown to both developer and admin.

---

## 7. Code Generation

The approved submission is injected into the boilerplate template using Jinja2.

**Template target:** `template/src/server.py`

```python
# AUTO-GENERATED — DO NOT EDIT MANUALLY
# Generated by MCP Factory from submission {{ submission_id }}

from mcp.server.fastmcp import FastMCP
from src.auth_context import get_auth

mcp = FastMCP("{{ project.name }}", stateless_http=True,
              streamable_http_path="/")

# ── User-supplied tools ────────────────────────────────────────────
{{ tools_code | indent(0) }}
```

Additional generated files:
- `pyproject.toml` — with detected dependencies injected
- `.env` — populated from Azure provisioning outputs (never committed)
- `README.md` — server-specific docs with MCP URL and connection guide

---

## 8. Azure Provisioning Pipeline

Triggered automatically after admin approval. Runs as an async ARQ task with live WebSocket status pushed to the frontend.

```
Step 1  Create Azure App Registration
        → expose scope: api://{client_id}/access_as_user
        → add redirect URIs (claude.ai, copilot studio, localhost)

Step 2  Create client secret
        → store in Azure Key Vault (never in DB or .env file in repo)

Step 3  Build Docker image
        → docker build from generated server code
        → tag: {acr_name}.azurecr.io/{project_name}:{submission_id[:8]}

Step 4  Push to Azure Container Registry

Step 5  Deploy to Azure Container Apps
        → inject Key Vault secret references as env vars
        → enable ingress on port 8080
        → configure health probe at /health

Step 6  Smoke test the live deployment
        → GET /health → must return 200
        → GET /.well-known/oauth-protected-resource → must return valid JSON

Step 7  Write deployment record to DB
        → store MCP URL, ACR image, ACA resource ID
        → notify developer via email/Teams
```

---

## 9. Phased Delivery Plan

### Phase 1 — Core Engine (Weeks 1–3)
> Goal: Code parsing and server generation work end-to-end, deployable manually.

- [ ] AST-based code parser (type hints, docstrings, imports, security patterns)
- [ ] Jinja2 server code generator (tools injected into boilerplate)
- [ ] Sandbox executor (Docker SDK, auto-mock, synthetic input generation)
- [ ] `pyproject.toml` dependency merger
- [ ] Unit tests for parser and generator
- [ ] CLI: `mcp-factory validate tools.py` and `mcp-factory generate tools.py`

**Deliverable:** Developer can run CLI to validate and generate a server locally.

---

### Phase 2 — Backend API & Approval Flow (Weeks 4–6)
> Goal: Full submission → approval → generated-code flow over REST API.

- [ ] PostgreSQL schema + Alembic migrations
- [ ] FastAPI project: CRUD for projects and submissions
- [ ] ARQ task queue wired to sandbox executor
- [ ] Submission state machine (status transitions + guards)
- [ ] Admin approval endpoints (approve / reject with comment)
- [ ] WebSocket endpoint for live sandbox log streaming
- [ ] Azure Entra JWT auth for all API routes
- [ ] Role-based access control (developer vs. admin)
- [ ] Teams / email notification on submission and decision
- [ ] API integration tests

**Deliverable:** Full approval flow testable via API (curl / Postman).

---

### Phase 3 — Web UI (Weeks 7–9)
> Goal: Developers and admins can use the platform through a browser.

- [ ] Next.js project scaffold with Azure Entra SSO (MSAL)
- [ ] Developer: Project list + create project page
- [ ] Developer: Code editor page (Monaco + real-time Layer 1 feedback)
- [ ] Developer: Tool preview panel (shows tool as LLM would see it)
- [ ] Developer: Submission history + status timeline
- [ ] Developer: Live sandbox log viewer (WebSocket)
- [ ] Admin: Approval queue page
- [ ] Admin: Submission detail (code view, validation reports, approve/reject form)
- [ ] Admin: All deployments overview
- [ ] Toast notifications + error boundaries

**Deliverable:** End-to-end demo: upload → validate → submit → approve (Azure provisioning still manual).

---

### Phase 4 — Azure Auto-Provisioning (Weeks 10–12)
> Goal: One-click deployment from approved submission to live MCP server.

- [ ] Azure SDK integration (App Registration, Key Vault, ACR, ACA)
- [ ] ARQ provisioning task with step-by-step status events
- [ ] Live provisioning progress page (WebSocket, step checklist)
- [ ] Smoke test runner against deployed URL
- [ ] Deployment record storage + MCP URL display
- [ ] Developer connection guide page (Claude.ai, Copilot Studio instructions)
- [ ] Admin: Force-undeploy / teardown action
- [ ] Error handling + retry logic for Azure API flakiness

**Deliverable:** Full automated pipeline, developer receives MCP URL after admin approves.

---

### Phase 5 — Operations & Governance (Weeks 13–15)
> Goal: Platform is production-ready for enterprise use.

- [ ] Server health dashboard (polls `/health` on each deployed server)
- [ ] Version management (resubmit → new version → re-approval)
- [ ] Audit log page (every state transition, who did what, when)
- [ ] Department-based access scoping
- [ ] Admin: Allowlist/blocklist for Python imports
- [ ] Rate limiting on sandbox execution (per user per day)
- [ ] Platform-level CI/CD (deploy the factory itself to ACA)
- [ ] Runbook and operations documentation

**Deliverable:** Production-hardened platform ready for enterprise rollout.

---

## 10. Key Design Boundaries

The platform guarantees:
- Code is syntactically correct Python
- Tool interfaces conform to MCP/FastMCP specification
- Basic execution does not crash with synthetic inputs
- No known dangerous patterns (shell exec, hardcoded secrets)

The platform **does not** guarantee:
- Business logic correctness — this is the developer's responsibility, enforced by their own tests (Layer 3)
- External API or database connectivity in production — those depend on the target environment
- Security of the tool's own logic — admin code review remains essential

---

## 11. Repository Structure (Proposed)

```
mcp-factory/
├── factory-backend/          # FastAPI application
│   ├── src/
│   │   ├── api/              # Route handlers
│   │   ├── core/
│   │   │   ├── parser/       # AST analysis
│   │   │   ├── generator/    # Jinja2 code gen
│   │   │   └── sandbox/      # Docker executor
│   │   ├── models/           # SQLAlchemy models
│   │   ├── tasks/            # ARQ async tasks
│   │   └── azure/            # Provisioning clients
│   ├── templates/            # Jinja2 server templates
│   │   └── server_py.j2
│   ├── tests/
│   ├── alembic/              # DB migrations
│   └── pyproject.toml
│
├── factory-frontend/         # Next.js application
│   ├── app/
│   │   ├── (developer)/
│   │   └── (admin)/
│   ├── components/
│   └── package.json
│
├── mcp-server-boilerplate/   # Existing — used as generation base
│
└── docker-compose.yml        # Local dev: backend + frontend + postgres + redis
```

---

## 12. Open Questions (Decide Before Phase 4)

| Question | Options |
|----------|---------|
| Who owns the Azure subscription for deployed servers? | Platform team's subscription vs. each department's own subscription |
| How are Azure credentials provided? | Admin pre-configures one SP per environment vs. each team provides their own |
| What happens when a developer leaves the company? | Transfer ownership, archive server, or auto-teardown? |
| Multi-environment support? | Dev / Staging / Prod approval chains, or single environment? |
| Billing / cost visibility? | Show estimated Azure cost per server before provisioning? |
