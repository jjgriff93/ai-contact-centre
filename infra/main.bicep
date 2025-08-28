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
      'OpenAI.GlobalStandard.gpt-4o-mini-transcribe,100'
      'OpenAI.GlobalStandard.gpt-4o-mini-tts,100'
      'OpenAI.GlobalStandard.gpt-4.1,150'
    ]
  }
})
param apiExists bool

@description('Id of the user or app to assign application roles')
param principalId string

@description('Tags that will be applied to all resources (pass in env var as JSON string with single quotes)')
param tags string = '{}'

// Tags that should be applied to all resources.
// 
// Note that 'azd-service-name' tags should be applied separately to service host resources.
// Example usage:
//   tags: union(tags, { 'azd-service-name': <service name in azure.yaml> })
var commonTags = union(json(tags), {
  'azd-env-name': environmentName
})

// Organize resources in a resource group
resource rg 'Microsoft.Resources/resourceGroups@2021-04-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: commonTags
}

module resources 'modules/container.bicep' = {
  scope: rg
  name: 'resources'
  params: {
    location: location
    tags: commonTags
    principalId: principalId
    apiExists: apiExists
    aiServicesEndpoint: aiModelsDeploy.outputs.AZURE_AI_SERVICES_ENDPOINT
    communicationServiceName: acs.outputs.AZURE_COMMUNICATION_SERVICE_NAME
    eventGridSystemTopicName: acs.outputs.AZURE_EVENT_GRID_SYSTEM_TOPIC
  }
}

module aiModelsDeploy 'modules/ai-project.bicep' = {
  scope: rg
  name: 'ai-project'
  params: {
    tags: commonTags
    location: location
    envName: environmentName
    principalId: principalId
    deployments: [
      {
        name: 'gpt-4o-realtime-preview'
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
      {
        name: 'gpt-4o-mini-transcribe'
        model: {
          name: 'gpt-4o-mini-transcribe'
          format: 'OpenAI'
          version: '2025-03-20'
        }
        sku: {
          name: 'GlobalStandard'
          capacity: 100
        }
      }
      {
        name: 'tts' // gpt-4o-mini-tts not currently available in Sweden Central
        model: {
          name: 'tts'
          format: 'OpenAI'
          version: '001'
        }
        sku: {
          name: 'Standard'
          capacity: 3
        }
      }
      {
        name: 'gpt-4.1'
        model: {
          name: 'gpt-4.1'
          format: 'OpenAI'
          version: '2025-04-14'
        }
        sku: {
          name: 'GlobalStandard'
          capacity: 150
        }
      }
    ]
  }
}

module acs 'modules/acs.bicep' = {
  scope: rg
  name: 'acs'
  params: {
    location: location
    tags: commonTags
  }
}

output AZURE_AI_PROJECT_ENDPOINT string = aiModelsDeploy.outputs.ENDPOINT
output AZURE_AI_SERVICES_ENDPOINT string = aiModelsDeploy.outputs.AZURE_AI_SERVICES_ENDPOINT
output AZURE_ACS_ENDPOINT string = acs.outputs.AZURE_COMMUNICATION_SERVICE_ENDPOINT
output AZURE_ACS_EVENT_GRID_SYSTEM_TOPIC string = acs.outputs.AZURE_EVENT_GRID_SYSTEM_TOPIC
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = resources.outputs.AZURE_CONTAINER_REGISTRY_ENDPOINT
output AZURE_CONTAINER_APP_URI string = resources.outputs.AZURE_CONTAINER_APP_URI
output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_RESOURCE_API_ID string = resources.outputs.AZURE_RESOURCE_API_ID
output AZURE_RESOURCE_STORAGE_ID string = resources.outputs.AZURE_RESOURCE_STORAGE_ID
output AZURE_RESOURCE_AI_PROJECT_ID string = aiModelsDeploy.outputs.projectId
