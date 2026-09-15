// ==========================================================================
// FinSolve RBAC RAG Chatbot — Azure infrastructure (Container Apps)
//
// Provisions:
//   * Log Analytics workspace          (centralised logs + metrics)
//   * Application Insights              (traces / request telemetry)
//   * Azure Container Registry (ACR)    (holds the app image)
//   * User-assigned managed identity    (ACR pull, no admin creds)
//   * Container Apps environment
//   * The chatbot Container App         (external ingress, autoscaling)
//
// The vector store (Milvus) is expected to be a managed endpoint — Zilliz Cloud
// (managed Milvus, has a free tier) or a self-hosted Milvus reachable at
// `milvusUri`. Azure OpenAI is referenced as an existing resource via params.
// ==========================================================================

@description('Deployment location.')
param location string = resourceGroup().location

@description('Short prefix for resource names, e.g. "finsolve".')
@minLength(3)
@maxLength(11)
param namePrefix string = 'finsolve'

@description('Application environment tag.')
@allowed(['staging', 'production'])
param appEnv string = 'production'

@description('Container image reference, e.g. <acr>.azurecr.io/finsolve-rbac-chatbot:<tag>.')
param containerImage string

// ---- Azure OpenAI (existing resource) ----
param azureOpenAiEndpoint string
@secure()
param azureOpenAiApiKey string
param azureOpenAiApiVersion string = '2024-10-21'
param chatDeployment string = 'gpt-4o'
param embeddingDeployment string = 'text-embedding-3-large'

// ---- Milvus / Zilliz ----
param milvusUri string
@secure()
param milvusToken string = ''
param milvusCollection string = 'finsolve_documents'

// ---- App secrets ----
@secure()
param jwtSecret string

@description('Optional Slack/Teams webhook for cost alerts.')
@secure()
param costAlertWebhookUrl string = ''

var tags = {
  application: 'finsolve-rbac-chatbot'
  environment: appEnv
}

// -------------------------------------------------------------------------- //
// Observability
// -------------------------------------------------------------------------- //
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${namePrefix}-logs'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: '${namePrefix}-appi'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
  }
}

// -------------------------------------------------------------------------- //
// Container registry + identity
// -------------------------------------------------------------------------- //
resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: '${namePrefix}acr'
  location: location
  tags: tags
  sku: { name: 'Basic' }
  properties: {
    adminUserEnabled: false
  }
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${namePrefix}-id'
  location: location
  tags: tags
}

// Grant the identity AcrPull on the registry.
var acrPullRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, identity.id, acrPullRoleId)
  scope: acr
  properties: {
    roleDefinitionId: acrPullRoleId
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// -------------------------------------------------------------------------- //
// Container Apps environment
// -------------------------------------------------------------------------- //
resource caEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${namePrefix}-env'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

// -------------------------------------------------------------------------- //
// The chatbot Container App
// -------------------------------------------------------------------------- //
resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${namePrefix}-app'
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identity.id}': {} }
  }
  properties: {
    managedEnvironmentId: caEnv.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
      }
      registries: [
        {
          server: acr.properties.loginServer
          identity: identity.id
        }
      ]
      secrets: [
        { name: 'azure-openai-api-key', value: azureOpenAiApiKey }
        { name: 'milvus-token', value: milvusToken }
        { name: 'jwt-secret', value: jwtSecret }
        { name: 'cost-webhook', value: costAlertWebhookUrl }
        { name: 'appinsights-connection', value: appInsights.properties.ConnectionString }
      ]
    }
    template: {
      containers: [
        {
          name: 'chatbot'
          image: containerImage
          resources: {
            cpu: json('1.0')
            memory: '2Gi'
          }
          env: [
            { name: 'APP_ENV', value: appEnv }
            { name: 'LOG_LEVEL', value: 'INFO' }
            { name: 'AZURE_OPENAI_ENDPOINT', value: azureOpenAiEndpoint }
            { name: 'AZURE_OPENAI_API_KEY', secretRef: 'azure-openai-api-key' }
            { name: 'AZURE_OPENAI_API_VERSION', value: azureOpenAiApiVersion }
            { name: 'AZURE_OPENAI_CHAT_DEPLOYMENT', value: chatDeployment }
            { name: 'AZURE_OPENAI_EMBEDDING_DEPLOYMENT', value: embeddingDeployment }
            { name: 'MILVUS_URI', value: milvusUri }
            { name: 'MILVUS_TOKEN', secretRef: 'milvus-token' }
            { name: 'MILVUS_COLLECTION', value: milvusCollection }
            { name: 'JWT_SECRET_KEY', secretRef: 'jwt-secret' }
            { name: 'COST_ALERT_WEBHOOK_URL', secretRef: 'cost-webhook' }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', secretRef: 'appinsights-connection' }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: { path: '/health', port: 8000 }
              initialDelaySeconds: 15
              periodSeconds: 30
            }
            {
              type: 'Readiness'
              httpGet: { path: '/ready', port: 8000 }
              initialDelaySeconds: 10
              periodSeconds: 20
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 5
        rules: [
          {
            name: 'http-concurrency'
            http: { metadata: { concurrentRequests: '20' } }
          }
        ]
      }
    }
  }
}

output containerAppFqdn string = app.properties.configuration.ingress.fqdn
output acrLoginServer string = acr.properties.loginServer
output appInsightsName string = appInsights.name
