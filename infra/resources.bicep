@description('The location used for all deployed resources')
param location string = resourceGroup().location

@description('Tags that will be applied to all resources')
param tags object = {}

param apiExists bool
param aiFoundryProjectEndpoint string

@description('Id of the user or app to assign application roles')
param principalId string

@description('Endpoint of the Azure Communication Service')
param acsEndpoint string

var abbrs = loadJsonContent('./abbreviations.json')
var resourceToken = uniqueString(subscription().id, resourceGroup().id, location)

// Monitor application with Azure Monitor
module monitoring 'br/public:avm/ptn/azd/monitoring:0.1.0' = {
  name: 'monitoring'
  params: {
    logAnalyticsName: '${abbrs.operationalInsightsWorkspaces}${resourceToken}'
    applicationInsightsName: '${abbrs.insightsComponents}${resourceToken}'
    applicationInsightsDashboardName: '${abbrs.portalDashboards}${resourceToken}'
    location: location
    tags: tags
  }
}
// Container registry
module containerRegistry 'br/public:avm/res/container-registry/registry:0.1.1' = {
  name: 'registry'
  params: {
    name: '${abbrs.containerRegistryRegistries}${resourceToken}'
    location: location
    tags: tags
    publicNetworkAccess: 'Enabled'
    roleAssignments: [
      {
        principalId: apiIdentity.outputs.principalId
        principalType: 'ServicePrincipal'
        roleDefinitionIdOrName: subscriptionResourceId(
          'Microsoft.Authorization/roleDefinitions',
          '7f951dda-4ed3-4680-a7ca-43fe172d538d'
        )
      }
    ]
  }
}

// Container apps environment
module containerAppsEnvironment 'br/public:avm/res/app/managed-environment:0.4.5' = {
  name: 'container-apps-environment'
  params: {
    logAnalyticsWorkspaceResourceId: monitoring.outputs.logAnalyticsWorkspaceResourceId
    name: '${abbrs.appManagedEnvironments}${resourceToken}'
    location: location
    zoneRedundant: false
  }
}
var storageAccountName = '${abbrs.storageStorageAccounts}${resourceToken}'
module storageAccount 'br/public:avm/res/storage/storage-account:0.17.2' = {
  name: 'storageAccount'
  params: {
    name: storageAccountName
    allowSharedKeyAccess: false
    publicNetworkAccess: 'Enabled'
    blobServices: {
      containers: [
        {
          name: 'eval'
        }
      ]
    }
    location: location
    roleAssignments: [
      {
        principalId: principalId
        principalType: 'User'
        roleDefinitionIdOrName: 'Storage Blob Data Contributor'
      }
      {
        principalId: apiIdentity.outputs.principalId
        principalType: 'ServicePrincipal'
        roleDefinitionIdOrName: 'Storage Blob Data Contributor'
      }
    ]
    networkAcls: {
      defaultAction: 'Allow'
    }
    tags: tags
  }
}

module apiIdentity 'br/public:avm/res/managed-identity/user-assigned-identity:0.2.1' = {
  name: 'apiidentity'
  params: {
    name: '${abbrs.managedIdentityUserAssignedIdentities}api-${resourceToken}'
    location: location
  }
}
module apiFetchLatestImage './modules/fetch-container-image.bicep' = {
  name: 'api-fetch-image'
  params: {
    exists: apiExists
    name: 'api'
  }
}

module api 'br/public:avm/res/app/container-app:0.8.0' = {
  name: 'api'
  params: {
    name: 'api'
    ingressTargetPort: 8000
    scaleMinReplicas: 1
    scaleMaxReplicas: 10
    secrets: {
      secureList: []
    }
    containers: [
      {
        image: apiFetchLatestImage.outputs.?containers[?0].?image ?? 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
        name: 'main'
        resources: {
          cpu: json('0.5')
          memory: '1.0Gi'
        }
        env: [
          {
            name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
            value: monitoring.outputs.applicationInsightsConnectionString
          }
          {
            name: 'AZURE_CLIENT_ID'
            value: apiIdentity.outputs.clientId
          }
          {
            name: 'AZURE_FOUNDRY_ENDPOINT'
            value: aiFoundryProjectEndpoint
          }
          {
            name: 'ACS_ENDPOINT'
            value: acsEndpoint
          }
          {
            name: 'ACS_CALLBACK_HOST_URI'
            value: '' // Set by azd post-provision hook to container app's URL after deployment
          }
        ]
      }
    ]
    managedIdentities: {
      systemAssigned: false
      userAssignedResourceIds: [apiIdentity.outputs.resourceId]
    }
    registries: [
      {
        server: containerRegistry.outputs.loginServer
        identity: apiIdentity.outputs.resourceId
      }
    ]
    environmentResourceId: containerAppsEnvironment.outputs.resourceId
    location: location
    tags: union(tags, { 'azd-service-name': 'api' })
  }
}

resource apibackendRoleAzureAIDeveloperRG 'Microsoft.Authorization/roleAssignments@2020-04-01-preview' = {
  name: guid(subscription().id, resourceGroup().id, apiIdentity.name, '64702f94-c441-49e6-a78b-ef80e0188fee')
  scope: resourceGroup()
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '64702f94-c441-49e6-a78b-ef80e0188fee'
    )
    principalId: apiIdentity.outputs.principalId
    principalType: 'ServicePrincipal'
  }
}

resource apibackendRoleCognitiveServicesUserRG 'Microsoft.Authorization/roleAssignments@2020-04-01-preview' = {
  name: guid(subscription().id, resourceGroup().id, apiIdentity.name, 'a97b65f3-24c7-4388-baec-2e87135dc908')
  scope: resourceGroup()
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      'a97b65f3-24c7-4388-baec-2e87135dc908'
    )
    principalId: apiIdentity.outputs.principalId
    principalType: 'ServicePrincipal'
  }
}

output AZURE_CONTAINER_REGISTRY_ENDPOINT string = containerRegistry.outputs.loginServer
output AZURE_RESOURCE_API_ID string = api.outputs.resourceId
output AZURE_RESOURCE_STORAGE_ID string = storageAccount.outputs.resourceId
output ACA_API_NAME string = api.outputs.name
output ACA_API_ENDPOINT string = api.outputs.fqdn
