from azure.communication.callautomation.aio import CallAutomationClient
from azure.identity import DefaultAzureCredential

from .config import settings

# Create ACS client using managed identity (or az cli identity when running locally)
acs_client = CallAutomationClient(settings.AZURE_ACS_ENDPOINT, DefaultAzureCredential()) # type: ignore

def get_acs_client():
    return acs_client
