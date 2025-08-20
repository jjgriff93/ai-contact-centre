import logging
from typing import Optional

from dotenv_azd import AzdCommandNotFoundError, load_azd_env
from pydantic import Field
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

# Load environment variables from azd .env file when present (for local development)
try:
    load_azd_env()
except AzdCommandNotFoundError as e:
    logging.warning(f"No azd cli present. Assuming environment variables are already set.")

class Settings(BaseSettings):
    AZURE_ACS_ENDPOINT: str = Field(..., description='Azure Communication Services endpoint')
    AZURE_AI_SERVICES_ENDPOINT: str = Field(..., description='Azure AI (Cognitive) Services endpoint')
    AZURE_ACS_CALLBACK_HOST_URI: Optional[str] = Field(None, description='Callback host URI for webhooks. If not specified will use the requests host URI.')
    MCP_ORDERS_URL: str = Field(..., description='URL for the Orders MCP server')

settings = Settings() # type: ignore
