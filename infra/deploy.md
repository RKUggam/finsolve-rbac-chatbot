# Azure deployment guide

This deploys the chatbot to **Azure Container Apps**, with logs/metrics in **Log
Analytics + Application Insights**, the image in **Azure Container Registry**, and
secrets injected as Container App secrets. The vector store is **managed Milvus
(Zilliz Cloud)**; Azure OpenAI is referenced as an existing resource.

> You run these commands — they need your Azure login and subscription.

## 0. Prerequisites

- Azure CLI (`az`) + Bicep (`az bicep install`)
- An Azure subscription with quota for Azure OpenAI
- An Azure OpenAI resource with two deployments: a chat model (e.g. `gpt-4o`)
  and an embedding model (e.g. `text-embedding-3-large`)
- A Zilliz Cloud (managed Milvus) cluster — free tier is fine — with its URI and API key

```bash
az login
az account set --subscription "<SUBSCRIPTION_ID>"
az group create --name finsolve-rg --location eastus
```

## 1. First-time bootstrap: create the registry, then push an image

The Bicep template creates the ACR, but you need an image in it before the
Container App can start. Two options:

**A. Let CI/CD do it** (recommended) — see `.github/workflows/cd.yml`. Push to
`main` and the pipeline builds, pushes, and deploys.

**B. Manual bootstrap:**

```bash
# Create just the ACR first (or deploy the full template; the app revision will
# simply fail to pull until an image exists, then auto-recover on next deploy).
az deployment group create \
  --resource-group finsolve-rg \
  --template-file infra/main.bicep \
  --parameters @infra/main.parameters.json \
  --parameters containerImage="mcr.microsoft.com/k8se/quickstart:latest"   # placeholder

ACR=$(az acr list -g finsolve-rg --query "[0].name" -o tsv)
az acr login --name "$ACR"
docker build -t "$ACR.azurecr.io/finsolve-rbac-chatbot:latest" .
docker push "$ACR.azurecr.io/finsolve-rbac-chatbot:latest"
```

## 2. Deploy (or redeploy) with real parameters

Copy `main.parameters.example.json` to `main.parameters.json` and fill in the
non-secret values. Pass secrets on the command line (or wire in Key Vault):

```bash
az deployment group create \
  --resource-group finsolve-rg \
  --template-file infra/main.bicep \
  --parameters @infra/main.parameters.json \
  --parameters \
      containerImage="$ACR.azurecr.io/finsolve-rbac-chatbot:latest" \
      azureOpenAiApiKey="$AZURE_OPENAI_API_KEY" \
      milvusToken="$ZILLIZ_TOKEN" \
      jwtSecret="$(python -c 'import secrets;print(secrets.token_urlsafe(48))')"

# The app URL:
az deployment group show -g finsolve-rg -n main \
  --query properties.outputs.containerAppFqdn.value -o tsv
```

## 3. Build the vector index (one-off ingestion job)

Ingestion runs against Azure OpenAI (embeddings) + your Milvus endpoint. Run it
once after the first deploy (and whenever `data/` changes) — locally or as an
`az containerapp job`:

```bash
# Locally, pointing at the managed endpoints:
export AZURE_OPENAI_ENDPOINT=... AZURE_OPENAI_API_KEY=... \
       MILVUS_URI=... MILVUS_TOKEN=...
python -m scripts.ingest
```

## 4. Monitoring

- **Logs:** Container App → Log stream, or Log Analytics (`ContainerAppConsoleLogs_CL`).
- **Metrics:** `GET /metrics` (Prometheus). Scrape with Azure Monitor managed
  Prometheus or Grafana. Key series: `finsolve_chat_requests_total`,
  `finsolve_cost_usd_total`, `finsolve_chat_blocked_total`, `finsolve_chat_latency_seconds`.
- **Cost alerts:** set `COST_ALERT_WEBHOOK_URL`; the app posts a message when the
  per-request or daily budget is exceeded. Also set an Azure **Cost Management**
  budget alert on the resource group as a backstop.
- **Traces (optional):** set `LANGCHAIN_TRACING_V2=true` + `LANGCHAIN_API_KEY`
  for LangSmith request tracing.

## 5. Evaluation gate

`cd.yml` runs `python -m evaluation.run_eval` against the staging revision before
promoting traffic. The deploy fails if RBAC leakage is detected, a denial/out-of-
scope case is not refused, or any Ragas metric falls below its threshold
(`evaluation/thresholds.json`).
