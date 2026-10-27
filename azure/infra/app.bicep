param prefix string
param location string = resourceGroup().location
@description('Immutable ACR image digest, e.g. registry.azurecr.io/event-horizon@sha256:...')
param image string
param functionUrl string
@secure()
param functionKey string
@secure()
@minLength(32)
param ingestToken string
@secure()
@minLength(32)
param operatorPassword string
param foundryEndpoint string = ''
param modelDeployment string = ''
var suffix = uniqueString(resourceGroup().id, prefix)
resource containerEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' existing = { name: '${prefix}-environment' }
resource insights 'Microsoft.Insights/components@2020-02-02' existing = { name: '${prefix}-monitor' }
resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = { name: '${prefix}-app-identity' }
resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = { name: '${prefix}${suffix}' }
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' existing = { name: take('${prefix}${suffix}',24) }
resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${prefix}-app'
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identity.id}': {} }
  }
  properties: {
    managedEnvironmentId: containerEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: { external: true, targetPort: 8000, allowInsecure: false, transport: 'http' }
      registries: [ { server: registry.properties.loginServer, identity: identity.id } ]
      secrets: [
        { name: 'function-key', value: functionKey }
        { name: 'ingest-token', value: ingestToken }
        { name: 'operator-password', value: operatorPassword }
        { name: 'monitor', value: insights.properties.ConnectionString }
      ]
    }
    template: {
                                                                             
                                                                               
      scale: { minReplicas: 1, maxReplicas: 1 }
      containers: [ {
        name: 'event-horizon'
        image: image
        resources: { cpu: 1, memory: '2Gi' }
        env: [
          { name: 'EVENT_HORIZON_INGRESS', value: 'functions' }
          { name: 'EVENT_HORIZON_FUNCTION_URL', value: functionUrl }
          { name: 'EVENT_HORIZON_FUNCTION_KEY', secretRef: 'function-key' }
          { name: 'EVENT_HORIZON_INGEST_TOKEN', secretRef: 'ingest-token' }
          { name: 'EVENT_HORIZON_PUBLIC_ORIGIN', value: 'https://${prefix}-app.${containerEnvironment.properties.defaultDomain}' }
          { name: 'EVENT_HORIZON_OPERATOR_PASSWORD', secretRef: 'operator-password' }
          { name: 'EVENT_HORIZON_AZURE_CREDENTIAL', value: 'managed_identity' }
          { name: 'AZURE_CLIENT_ID', value: identity.properties.clientId }
          { name: 'AZURE_AI_PROJECT_ENDPOINT', value: foundryEndpoint }
          { name: 'AZURE_AI_MODEL_DEPLOYMENT_NAME', value: modelDeployment }
          { name: 'EVENT_HORIZON_NARRATIVE_PROVIDER', value: empty(foundryEndpoint) ? 'local' : 'foundry' }
          { name: 'EVENT_HORIZON_BLOB_ACCOUNT_URL', value: storage.properties.primaryEndpoints.blob }
          { name: 'EVENT_HORIZON_BLOB_CONTAINER', value: 'match-evidence' }
          { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', secretRef: 'monitor' }
          { name: 'OTEL_SERVICE_NAME', value: 'event-horizon-app' }
        ]
        probes: [
          { type: 'Startup', httpGet: { path: '/health/live', port: 8000 }, initialDelaySeconds: 5, periodSeconds: 5, failureThreshold: 60 }
          { type: 'Liveness', httpGet: { path: '/health/live', port: 8000 }, periodSeconds: 30, failureThreshold: 3 }
          { type: 'Readiness', httpGet: { path: '/health/ready', port: 8000 }, periodSeconds: 10, failureThreshold: 3 }
        ]
      } ]
    }
  }
}
output appName string = app.name
output url string = 'https://${app.properties.configuration.ingress.fqdn}'
