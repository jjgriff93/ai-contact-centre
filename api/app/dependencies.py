from azure.communication.callautomation.aio import CallAutomationClient
from azure.identity import DefaultAzureCredential

from .config import settings


def get_acs_client():
    return CallAutomationClient(settings.AZURE_ACS_ENDPOINT, DefaultAzureCredential()) # pyright: ignore[reportArgumentType]
