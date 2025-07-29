targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the environment that can be used as part of naming resource convention')
param environmentName string

@minLength(1)
@description('Primary location for all resources (filtered on available regions for Voice Live).')
@allowed([
  'eastus2'
  'swedencentral'
])
param location string

@metadata({
  azd: {
    type: 'location'
    usageName: [
      'OpenAI.GlobalStandard.gpt-4o-realtime-preview,5'
    ]
  }
})
param apiExists bool

@description('Id of the user or app to assign application roles')
param principalId string

// Tags that should be applied to all resources.
// 
// Note that 'azd-service-name' tags should be applied separately to service host resources.
// Example usage:
//   tags: union(tags, { 'azd-service-name': <service name in azure.yaml> })
var tags = {
  'azd-env-name': environmentName
}

// Organize resources in a resource group
resource rg 'Microsoft.Resources/resourceGroups@2021-04-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

module resources 'resources.bicep' = {
  scope: rg
  name: 'resources'
  params: {
    location: location
    tags: tags
    principalId: principalId
    apiExists: apiExists
    aiFoundryProjectEndpoint: aiModelsDeploy.outputs.ENDPOINT
    communicationServiceName: acs.outputs.AZURE_COMMUNICATION_SERVICE_NAME
  }
}

module aiModelsDeploy 'ai-project.bicep' = {
  scope: rg
  name: 'ai-project'
  params: {
    tags: tags
    location: location
    envName: environmentName
    principalId: principalId
    deployments: [
      {
        name: 'gpt4oRealtimePreviewDeployment'
        model: {
          name: 'gpt-4o-realtime-preview'
          format: 'OpenAI'
          version: '2025-06-03'
        }
        sku: {
          name: 'GlobalStandard'
          capacity: 5
        }
      }
    ]
  }
}

module acs 'acs.bicep' = {
  scope: rg
  name: 'acs'
  params: {
    location: location
    tags: tags
  }
}
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = resources.outputs.AZURE_CONTAINER_REGISTRY_ENDPOINT
output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_RESOURCE_API_ID string = resources.outputs.AZURE_RESOURCE_API_ID
output AZURE_RESOURCE_STORAGE_ID string = resources.outputs.AZURE_RESOURCE_STORAGE_ID
output AZURE_AI_PROJECT_ENDPOINT string = aiModelsDeploy.outputs.ENDPOINT
output AZURE_RESOURCE_AI_PROJECT_ID string = aiModelsDeploy.outputs.projectId
output AZURE_ACS_EVENT_GRID_SYSTEM_TOPIC string = acs.outputs.AZURE_EVENT_GRID_SYSTEM_TOPIC
