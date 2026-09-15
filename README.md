# FinSolve — Internal RAG Chatbot with Role-Based Access Control

An internal knowledge assistant for **FinSolve Technologies** (FinTech). Employees
ask natural-language questions and get grounded, cited answers drawn **only from
the company documents their role is allowed to see**. Built as a production system:
authentication, RBAC enforced at the data layer, safety guardrails, cost
monitoring, an automated evaluation gate, and one-command Azure deployment.

> Codebasics **DS-RPC-01** challenge, extended to production requirements
> (guardrails, Azure deploy, monitoring, cost tracking, CI/CD eval gate).

---

## Table of contents
- [What it does](#what-it-does)
- [Architecture](#architecture)
- [Roles & permissions](#roles--permissions)
- [Tech stack](#tech-stack)
- [Project layout](#project-layout)
- [Quick start (local)](#quick-start-local)
- [Usage examples](#usage-examples)
- [Guardrails](#guardrails)
- [Monitoring & cost tracking](#monitoring--cost-tracking)
- [Evaluation gate](#evaluation-gate)
- [Deployment (Azure)](#deployment-azure)
- [Testing](#testing)
- [Configuration reference](#configuration-reference)
- [Design choices & extensibility](#design-choices--extensibility)

---

## What it does

- **Authenticates** users (JWT sessions) and assigns each a **role**.
- **Retrieves** relevant chunks from a Milvus vector store, **pre-filtered by role**
  so the LLM never sees documents the user isn't entitled to.
- **Generates** a concise, grounded answer with **inline source citations**.
- **Guards** every request: prompt-injection / out-of-scope detection on input,
  **PII redaction** on output.
- **Tracks** token usage and **USD cost** per request, with budget alerts.
- **Evaluates** itself on every deploy (RBAC-leakage + behavioural + Ragas quality
  gates) so a regression blocks the release.

## Architecture

```
                         ┌──────────────────────────────────────────────┐
   Browser  ───login───► │  FastAPI  (single deployable service)         │
   (chat UI)             │                                               │
        ▲                │  /auth      JWT auth  ── UserRepository        │
        │  answer +      │  /api/chat  ─────────────┐                     │
        └──citations──── │  /,  /chat  Jinja2 UI     │                    │
                         │  /metrics   Prometheus    ▼                    │
                         │                     RAG pipeline               │
                         │   guardrails → RBAC retrieve → LLM → redact    │
                         │        │            │            │             │
                         └────────┼────────────┼────────────┼────────────┘
                                  │            │            │
                       scope/PII  │   role→dept filter      │ Azure OpenAI
                                  │            ▼            ▼ (chat + embeddings)
                                  │       ┌─────────┐
                                  │       │ Milvus  │  vectors + department metadata
                                  │       └─────────┘
                          cost + metrics ──► Log Analytics / Prometheus
```

Access control is enforced **at retrieval** (a Milvus filter expression built from
the role), not merely in the prompt — the single strongest RBAC guarantee. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full data flow.

## Roles & permissions

Roles map to the departments (data folders) they may read. Defined once in
[`app/rbac/policy.py`](app/rbac/policy.py) — the single source of truth.

| Role | Finance | Marketing | HR | Engineering | General |
|------|:---:|:---:|:---:|:---:|:---:|
| **C-Level** (`cfo`) | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Finance** (`finance.lead`) | ✅ | | | | ✅ |
| **Marketing** (`marketing.lead`) | | ✅ | | | ✅ |
| **HR** (`hr.lead`) | | | ✅ | | ✅ |
| **Engineering** (`eng.lead`) | | | | ✅ | ✅ |
| **Employee** (`employee`) | | | | | ✅ |

*General* = company-wide policies, handbook, FAQs — visible to everyone.

**Demo accounts** (local only) — password `FinSolve@2024` for all. Defined in
[`app/auth/users_seed.json`](app/auth/users_seed.json). Replace this with a real
identity provider for production (see [Design choices](#design-choices--extensibility)).

## Tech stack

| Layer | Choice |
|-------|--------|
| Language / runtime | Python 3.11 |
| API + UI | FastAPI (serves REST API **and** the Jinja2 chat UI — one service) |
| RAG framework | LangChain |
| Vector DB | Milvus (local via Docker; Zilliz Cloud managed in prod) |
| LLM + embeddings | Azure OpenAI (`gpt-4o` + `text-embedding-3-large`) |
| Auth | JWT (PyJWT) + bcrypt (passlib) |
| Guardrails | Presidio (PII) with regex fallback + rule-based scope/injection |
| Evaluation | Ragas + deterministic RBAC & behavioural gates |
| Monitoring | structlog (JSON), Prometheus (`/metrics`), token-cost tracker |
| Cloud | Azure Container Apps, ACR, Log Analytics, App Insights (Bicep IaC) |
| CI/CD | GitHub Actions (lint/test → build → deploy → ingest → eval gate → promote) |

## Project layout

```
app/
  main.py              FastAPI app: routers, middleware, health, /metrics
  config.py            Validated settings (pydantic-settings)
  logging_config.py    structlog JSON logging + request correlation id
  auth/                JWT, password hashing, user repository, /auth routes
  rbac/policy.py       Role → Department access rules (single source of truth)
  rag/
    providers.py       Azure OpenAI chat + embeddings factories
    vectorstore.py     Milvus wrapper (department as filterable field)
    ingestion.py       Load data/, chunk, tag, embed
    retriever.py       RBAC-filtered retrieval
    prompts.py         System/user prompts
    pipeline.py        Orchestration: guardrails → retrieve → generate → redact
  guardrails/          pii.py (redaction), scope.py (injection/out-of-scope)
  monitoring/          cost.py (tokens + USD + alerts), metrics.py (Prometheus)
  api/chat.py          Authenticated /api/chat endpoint
  web.py, templates/, static/   Server-rendered chat UI
scripts/               ingest.py (build index), hash_password.py
evaluation/            golden_dataset.jsonl, thresholds.json, run_eval.py
infra/                 main.bicep, parameters, deploy.md
tests/                 hermetic unit + API tests (no external services)
.github/workflows/     ci.yml, cd.yml
data/                  company documents (finance, marketing, hr, engineering, general)
```

## Quick start (local)

**Prerequisites:** Python 3.11, Docker Desktop, and an Azure OpenAI resource with a
chat deployment + an embedding deployment.

```bash
# 1. Configure
cp .env.example .env
#    edit .env: set AZURE_OPENAI_ENDPOINT / _API_KEY / deployment names,
#    and a real JWT_SECRET_KEY  (python -c "import secrets; print(secrets.token_urlsafe(48))")

# 2. Install
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt

# 3. Start Milvus (standalone) — Milvus Lite isn't supported on Windows
docker compose up -d etcd minio milvus

# 4. Build the vector index from data/
python -m scripts.ingest

# 5. Run the app (API + UI)
uvicorn app.main:app --reload
```

Open <http://localhost:8000>, sign in as e.g. `finance.lead` / `FinSolve@2024`.

> On Windows without `make`, run the commands above directly. With Git Bash/WSL,
> `make help` lists shortcuts (`make milvus-up`, `make ingest`, `make run`, `make test`).

## Usage examples

Ask questions appropriate to your role — the assistant cites its sources:

- **Finance:** *"By what percentage did revenue grow in 2024?"* →
  *"Revenue grew by 25% in 2024… (source: Financial Summary)"*
- **Marketing:** *"What was the ROI of our digital campaigns?"*
- **HR:** *"What fields are in the employee dataset?"*
- **Employee:** *"What are the company's core values?"*

RBAC in action — a **marketing** user asking *"show me employee salaries"* gets:
*"I couldn't find anything in the documents you're authorised to access…"* because
HR data is never retrieved for that role.

API (bearer token):

```bash
TOKEN=$(curl -s localhost:8000/auth/login -H 'Content-Type: application/json' \
  -d '{"username":"finance.lead","password":"FinSolve@2024"}' | jq -r .access_token)

curl -s localhost:8000/api/chat -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"message":"What was the total vendor services spend in 2024?"}' | jq
```

## Guardrails

Configured via `GUARDRAILS_*` env vars; implemented in [`app/guardrails/`](app/guardrails).

- **Input — prompt injection & out-of-scope** ([`scope.py`](app/guardrails/scope.py)):
  attempts to override instructions, escalate access, or ask off-domain questions
  are blocked before any retrieval/LLM call.
- **Input — RBAC:** retrieval is pre-filtered to allowed departments; forbidden
  data is never fetched. "No accessible context" → a safe refusal.
- **Output — PII** ([`pii.py`](app/guardrails/pii.py)): answers are scrubbed of
  emails, phone numbers, SSNs, credit cards, PAN, Aadhaar (Presidio when available,
  regex fallback otherwise) so sensitive identifiers don't leak into responses/logs.

## Monitoring & cost tracking

- **Structured logs** (`structlog`) — JSON in production, one correlation id per
  request; ready for Azure Log Analytics.
- **Prometheus metrics** at `GET /metrics`: `finsolve_chat_requests_total`,
  `finsolve_chat_blocked_total`, `finsolve_tokens_total`, `finsolve_cost_usd_total`,
  `finsolve_chat_latency_seconds`, `finsolve_retrieved_docs`.
- **Cost tracking** ([`app/monitoring/cost.py`](app/monitoring/cost.py)): tokens are
  priced with configurable per-1K rates; a per-request cap and a rolling **daily
  budget** raise WARNING logs and optionally POST to a Slack/Teams webhook
  (`COST_ALERT_WEBHOOK_URL`). Current daily spend is exposed on `/ready`.
- **Tracing (optional):** set `LANGCHAIN_TRACING_V2=true` + `LANGCHAIN_API_KEY` for
  LangSmith.

## Evaluation gate

`python -m evaluation.run_eval` runs three gates against
[`evaluation/golden_dataset.jsonl`](evaluation/golden_dataset.jsonl):

1. **RBAC leakage (hard gate):** every query is checked to confirm retrieval never
   returns a forbidden department. A single leak fails the build.
2. **Behavioural (hard gate):** access-denial and out-of-scope questions must be
   refused with no forbidden data disclosed.
3. **RAG quality (Ragas):** faithfulness, answer relevancy, context precision &
   recall, gated by [`evaluation/thresholds.json`](evaluation/thresholds.json).

A JSON report is written to `evaluation/reports/`. In CI this runs after each
deploy and **blocks traffic promotion** on failure.

## Deployment (Azure)

Full infrastructure-as-code (Bicep) + GitHub Actions. See
**[infra/deploy.md](infra/deploy.md)** for the step-by-step guide.

- `infra/main.bicep` provisions Container Apps env, the app (external ingress,
  autoscale, health probes), ACR, managed identity (ACR pull), Log Analytics &
  App Insights. Secrets are Container App secrets.
- `.github/workflows/cd.yml`: build → push (ACR) → deploy → re-ingest → **eval
  gate** → promote 100% traffic to the new revision only if the gate passes.
- Managed **Milvus** = Zilliz Cloud; **Azure OpenAI** referenced via parameters.

## Testing

```bash
pytest                       # hermetic unit + API tests (no Azure/Milvus needed)
pytest --cov=app             # with coverage
ruff check app && mypy app   # lint + types
```

Tests mock the LLM and vector store, so they run offline and in CI on every push.

## Configuration reference

Every setting lives in [`.env.example`](.env.example) and is validated in
[`app/config.py`](app/config.py). Highlights:

| Variable | Purpose |
|----------|---------|
| `AZURE_OPENAI_ENDPOINT` / `_API_KEY` | Azure OpenAI credentials |
| `AZURE_OPENAI_CHAT_DEPLOYMENT` / `_EMBEDDING_DEPLOYMENT` | Deployment names |
| `MILVUS_URI` / `MILVUS_TOKEN` | Vector store (local or Zilliz) |
| `JWT_SECRET_KEY` | Session token signing (**must** be set in prod) |
| `RETRIEVAL_TOP_K`, `CHUNK_SIZE`, `CHUNK_OVERLAP` | Retrieval tuning |
| `COST_*` | Pricing rates, daily budget, per-request cap, alert webhook |
| `GUARDRAILS_PII_ENABLED` / `GUARDRAILS_SCOPE_ENABLED` | Toggle guardrails |

In `APP_ENV=production` the app **fails fast** if the JWT secret is still the
default or Azure OpenAI credentials are missing.

## Design choices & extensibility

- **RBAC at the data layer.** The role → department policy produces a Milvus filter,
  so forbidden documents are never retrieved — defense that doesn't depend on the
  LLM behaving. Adding a role or department is a one-line change in `policy.py`.
- **One deployable service.** FastAPI serves both the API and the UI, so there's a
  single container, single image, single scaling unit — simplest to run and deploy.
- **Provider-agnostic core.** LLM/embeddings live behind `providers.py` and the
  vector store behind `vectorstore.py`; swapping Azure OpenAI or Milvus touches
  only those files.
- **Pluggable identity.** `UserRepository` is the only auth touch-point — replace
  the JSON seed with Entra ID / a database without changing routes or the pipeline.
- **Scales out.** Stateless app (JWT sessions) → autoscale replicas; Milvus/Zilliz
  scales independently; ingestion is idempotent and re-runnable.
- **Safe by default in CI.** Every deploy must pass the RBAC-leakage, behavioural,
  and Ragas gates before serving traffic.
