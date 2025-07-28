@description('The location used for all deployed resources')
param location string = resourceGroup().location

@description('Tags that will be applied to all resources')
param tags object = {}

var resourceToken = uniqueString(subscription().id, resourceGroup().id, location)

module communicationService 'br/public:avm/res/communication/communication-service:0.4.0' = {
  name: 'acs'
  params: {
    dataLocation: 'Europe'
    name: 'acs-${resourceToken}'
    location: 'global'
    managedIdentities: { systemAssigned: true }
  }
}

resource eventGridSystemTopic 'Microsoft.EventGrid/systemTopics@2022-06-15' = {
  name: '${communicationService.name}-system-topic'
  location: location
  tags: tags
  properties: {
    source: resourceId('Microsoft.Communication/CommunicationServices', communicationService.name)
    topicType: 'Microsoft.Communication.CommunicationServices'
  }
}
// NOTE: Event Grid Subscription for Call Events must be created after deployment as it needs live subscriber endpoint to validate
output AZURE_EVENT_GRID_SYSTEM_TOPIC string = eventGridSystemTopic.name
output ACS_ENDPOINT string = communicationService.outputs.endpoint
