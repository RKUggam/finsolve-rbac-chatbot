# Architecture

## Request lifecycle (`POST /api/chat`)

1. **Auth** — `get_current_user` extracts the JWT from the `Authorization` header
   or the `access_token` cookie, validates the signature/expiry, and resolves the
   `User` (with `Role`). Unauthenticated requests get `401`.
2. **Input guardrails** — `scope.detect_prompt_injection` and `scope.is_out_of_scope`
   run first. A hit short-circuits to a safe refusal (no retrieval, no LLM cost).
3. **RBAC retrieval** — `retriever.retrieve` turns the role into a Milvus filter
   (`department in [...]`) via `rbac.policy.allowed_department_values`, then runs a
   similarity search. Only permitted departments are ever searched.
4. **No-context guard** — if nothing is retrieved, return a safe "no accessible
   information" message instead of hallucinating.
5. **Generation** — retrieved chunks become a numbered context block; the LLM is
   instructed to answer *only* from context and cite sources.
6. **Output guardrails** — `pii.redact` scrubs PII from the answer.
7. **Accounting** — token usage (from the model's `usage_metadata`, or a tiktoken
   estimate) → USD cost → `cost_tracker` (budget alerts) + Prometheus counters.
8. **Response** — answer, deduped citations, and usage returned to the caller.

## Why RBAC is enforced at retrieval

Prompt-only access control ("don't reveal HR data") is brittle — a clever prompt
can talk the model into leaking. Here the **vector search itself is filtered** by
the caller's role, so documents outside their permission set are never fetched and
never reach the model. `policy.py` is the single source of truth consumed by both
the retriever and the API response (`accessible_departments`), and by the
evaluation harness's leakage gate — the three can't drift.

## Data & ingestion

`data/<department>/…` — the folder name **is** the access-control label. Ingestion
([`app/rag/ingestion.py`](../app/rag/ingestion.py)) tags every chunk with
`department`, `source`, and `title`. Markdown is split with a
`RecursiveCharacterTextSplitter`; the HR CSV is expanded to one document per
employee so row-level facts survive chunking. Re-running ingestion rebuilds the
collection idempotently (`drop_old=True`).

## Components

| Concern | Module | Swap point |
|---------|--------|-----------|
| Config | `app/config.py` | env vars |
| Auth | `app/auth/*` | `UserRepository` → Entra ID / DB |
| Access policy | `app/rbac/policy.py` | edit the role→dept map |
| LLM / embeddings | `app/rag/providers.py` | any LangChain chat/embeddings |
| Vector store | `app/rag/vectorstore.py` | any LangChain vector store |
| Guardrails | `app/guardrails/*` | add recognisers / rules |
| Cost & metrics | `app/monitoring/*` | Prometheus / Log Analytics |

## Scaling

The app is **stateless** (JWT sessions, no server-side session store), so Azure
Container Apps scales it horizontally on HTTP concurrency (1→5 replicas by
default). Milvus/Zilliz scales independently. Heavy work (embedding the corpus)
happens offline in the ingestion job, not on the request path — only the query is
embedded per request.

## Failure modes

- **Azure OpenAI down** → generation raises; request returns `5xx`, logged with the
  correlation id; `/ready` reports degraded.
- **Milvus down** → retrieval raises; surfaced as an error (not a silent empty
  answer), so monitoring catches it.
- **Cost spike** → per-request and daily-budget alerts fire (log + webhook);
  Azure Cost Management budget is the backstop.
- **Quality regression** → the CI eval gate blocks traffic promotion.
