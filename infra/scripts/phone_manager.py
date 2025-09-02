#!/usr/bin/env python3
# /// script
# dependencies = [
#   "azure-communication-phonenumbers>=1.2.0",
#   "azure-identity>=1.23.0",
#   "pydantic>=2.0.0",
# ]
# ///
"""
Azure Communication Services Phone Number Management

This module provides functionality to purchase and manage phone numbers
for Azure Communication Services resources using the Azure SDK.

Production Features:
- Comprehensive error handling with Azure-specific exceptions
- Input validation for phone numbers and country codes
- Structured logging for monitoring and debugging
- Type hints for better code maintainability
"""

import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum

from azure.communication.phonenumbers import (
    PhoneNumbersClient,
    PhoneNumberType,
    PhoneNumberAssignmentType,
    PhoneNumberCapabilities,
    PhoneNumberCapabilityType
)
from azure.identity import DefaultAzureCredential
from azure.core.exceptions import HttpResponseError
from pydantic import BaseModel, Field


# Get logger without configuring it (let the application configure logging)
logger = logging.getLogger(__name__)


class CountryCode(str, Enum):
    """
    Common country codes for phone number purchasing.
    Note: This is not exhaustive. Azure supports additional countries.
    The Azure API will validate country support dynamically.
    """
    US = "US"
    CA = "CA" 
    GB = "GB"
    AU = "AU"
    FR = "FR"
    DE = "DE"
    IT = "IT"
    ES = "ES"
    NL = "NL"
    SE = "SE"
    NO = "NO"
    DK = "DK"
    FI = "FI"
    IE = "IE"
    CH = "CH"
    AT = "AT"
    BE = "BE"
    PT = "PT"
    
    @classmethod
    def from_string(cls, country_code: str) -> str:
        """
        Convert string to country code, returning the string value.
        This allows support for countries not explicitly listed in the enum.
        The Azure API will validate if the country is actually supported.
        """
        country_upper = country_code.upper()
        try:
            # Try to get the enum member
            return cls(country_upper).value
        except ValueError:
            # Return the string directly for countries not in enum
            # Azure API will validate actual support
            return country_upper


@dataclass
class SimplePhoneNumberResult:
    """Simple result of phone number operations"""
    phone_number: str
    country_code: str
    phone_number_type: str
    assignment_type: str
    capabilities: Dict[str, str]
    cost: Optional[float] = None
    currency: Optional[str] = None
    search_id: Optional[str] = None


class PhoneNumberPurchaseRequest(BaseModel):
    """Request model for phone number purchase"""
    country_code: str = Field(default="GB", description="Country code for phone number (2-letter ISO code)")
    toll_free: bool = Field(default=True, description="Whether to search for toll-free numbers")
    quantity: int = Field(default=1, ge=1, le=1, description="Number of phone numbers to search for (max 1)")
    area_code: Optional[str] = Field(None, description="Preferred area code (US/CA only)")
    calling_enabled: bool = Field(default=True, description="Enable calling capability")
    sms_enabled: bool = Field(default=False, description="Enable SMS capability (not supported for all countries/types)")


class SimplePhoneNumberManager:
    """Simplified phone number manager for Azure Communication Services"""
    
    def __init__(self, endpoint: str, credential: Optional[DefaultAzureCredential] = None):
        """
        Initialize the phone number manager
        
        Args:
            endpoint: Azure Communication Services endpoint
            credential: Azure credential (uses DefaultAzureCredential if None)
        
        Raises:
            ValueError: If endpoint is invalid
        """
        if not endpoint or not endpoint.startswith('https://'):
            raise ValueError("Invalid endpoint: must be a valid HTTPS URL")
        
        self.endpoint = endpoint.rstrip('/')
        self.credential = credential or DefaultAzureCredential()
        
        try:
            self.client = PhoneNumbersClient(self.endpoint, self.credential)
        except Exception as e:
            logger.error(f"Failed to initialize PhoneNumbersClient: {e}")
            raise ValueError(f"Failed to initialize phone numbers client: {e}") from e
        
    def search_available_phone_numbers(
        self,
        request: PhoneNumberPurchaseRequest
    ) -> List[SimplePhoneNumberResult]:
        """
        Search for available phone numbers (synchronous)
        
        Args:
            request: Phone number purchase request
            
        Returns:
            List of available phone numbers
        """
        try:
            # Determine phone number type
            phone_number_type = PhoneNumberType.TOLL_FREE if request.toll_free else PhoneNumberType.GEOGRAPHIC
            
            # Set up capabilities
            capabilities = PhoneNumberCapabilities(
                calling=PhoneNumberCapabilityType.INBOUND_OUTBOUND if request.calling_enabled else PhoneNumberCapabilityType.NONE,
                sms=PhoneNumberCapabilityType.INBOUND_OUTBOUND if request.sms_enabled else PhoneNumberCapabilityType.NONE
            )
            
            logger.info(f"Searching for {request.quantity} phone numbers in {request.country_code}")
            
            # Start search operation
            search_poller = self.client.begin_search_available_phone_numbers(
                country_code=request.country_code,
                phone_number_type=phone_number_type,
                assignment_type=PhoneNumberAssignmentType.APPLICATION,
                capabilities=capabilities,
                quantity=request.quantity,
                area_code=request.area_code
            )
            
            # Wait for search to complete
            search_result = search_poller.result()
            
            # Convert results
            results = []
            if hasattr(search_result, 'phone_numbers'):
                for phone_number in search_result.phone_numbers:
                    result = SimplePhoneNumberResult(
                        phone_number=phone_number,
                        country_code=request.country_code,
                        phone_number_type=phone_number_type.value if phone_number_type else "unknown",
                        assignment_type=PhoneNumberAssignmentType.APPLICATION.value,
                        capabilities={
                            "calling": capabilities.calling.value if capabilities.calling else "none",
                            "sms": capabilities.sms.value if capabilities.sms else "none"
                        },
                        cost=getattr(search_result.cost, 'amount', None) if hasattr(search_result, 'cost') and search_result.cost else None,
                        currency=getattr(search_result.cost, 'currency_code', None) if hasattr(search_result, 'cost') and search_result.cost else None,
                        search_id=getattr(search_result, 'search_id', None)
                    )
                    results.append(result)
            
            logger.info(f"Found {len(results)} available phone numbers")
            return results
            
        except HttpResponseError as e:
            logger.error(f"Failed to search phone numbers: {e}")
            raise e
        except Exception as e:
            logger.error(f"Unexpected error during phone number search: {e}")
            raise e
    
    def purchase_phone_number_by_search_id(self, search_id: str) -> Dict[str, Any]:
        """
        Purchase phone numbers using a search ID
        
        Args:
            search_id: Search ID from previous search
            
        Returns:
            Purchase result information
        """
        try:
            logger.info(f"Purchasing phone numbers with search ID: {search_id}")
            
            # Start purchase operation
            purchase_poller = self.client.begin_purchase_phone_numbers(search_id)
            
            # Wait for purchase to complete
            purchase_result = purchase_poller.result()
            
            result = {
                "status": "purchased",
                "search_id": search_id,
                "message": "Phone numbers purchased successfully",
                "purchase_result": str(purchase_result) if purchase_result else None
            }
            
            logger.info(f"Successfully purchased phone numbers with search ID: {search_id}")
            return result
            
        except HttpResponseError as e:
            logger.error(f"Failed to purchase phone numbers with search ID {search_id}: {e}")
            return {
                "status": "failed",
                "search_id": search_id,
                "error": str(e),
                "message": "Failed to purchase phone numbers"
            }
        except Exception as e:
            logger.error(f"Unexpected error during phone number purchase: {e}")
            raise e
    
    def purchase_random_phone_number(
        self,
        request: PhoneNumberPurchaseRequest
    ) -> Dict[str, Any]:
        """
        Search for available phone numbers and purchase them
        
        Args:
            request: Phone number purchase request
            
        Returns:
            Purchase result information
        """
        try:
            # Search for available numbers
            available_numbers = self.search_available_phone_numbers(request)
            
            if not available_numbers:
                return {
                    "status": "failed",
                    "message": "No available phone numbers found for the specified criteria"
                }
            
            # Get the search ID from the first result (they should all have the same search ID)
            search_id = available_numbers[0].search_id
            if not search_id:
                return {
                    "status": "failed",
                    "message": "No search ID available for purchase"
                }
            
            # Purchase using search ID
            purchase_result = self.purchase_phone_number_by_search_id(search_id)
            
            # Add search information to result
            purchase_result.update({
                "available_numbers": len(available_numbers),
                "searched_numbers": [
                    {
                        "phone_number": num.phone_number,
                        "type": num.phone_number_type,
                        "cost": num.cost,
                        "currency": num.currency
                    } for num in available_numbers
                ]
            })
            
            return purchase_result
            
        except Exception as e:
            logger.error(f"Failed to purchase random phone number: {e}")
            return {
                "status": "failed",
                "error": str(e),
                "message": "Failed to purchase random phone number"
            }
    
    def list_purchased_phone_numbers(self) -> List[Dict[str, Any]]:
        """
        List all purchased phone numbers for the ACS resource
        
        Returns:
            List of purchased phone numbers with their details
        """
        try:
            logger.info("Listing purchased phone numbers")
            
            purchased_numbers = []
            for phone_number_item in self.client.list_purchased_phone_numbers():
                number_info = {
                    "phone_number": phone_number_item.phone_number,
                    "country_code": phone_number_item.country_code,
                    "phone_number_type": str(phone_number_item.phone_number_type) if phone_number_item.phone_number_type else None,
                    "assignment_type": str(phone_number_item.assignment_type) if phone_number_item.assignment_type else None,
                    "capabilities": {
                        "calling": str(phone_number_item.capabilities.calling) if phone_number_item.capabilities and phone_number_item.capabilities.calling else None,
                        "sms": str(phone_number_item.capabilities.sms) if phone_number_item.capabilities and phone_number_item.capabilities.sms else None
                    },
                    "cost": phone_number_item.cost.amount if phone_number_item.cost else None,
                    "currency": phone_number_item.cost.currency_code if phone_number_item.cost else None
                }
                purchased_numbers.append(number_info)
            
            logger.info(f"Found {len(purchased_numbers)} purchased phone numbers")
            return purchased_numbers
            
        except HttpResponseError as e:
            logger.error(f"Failed to list purchased phone numbers: {e}")
            raise e
        except Exception as e:
            logger.error(f"Unexpected error listing phone numbers: {e}")
            raise e
    
    def release_phone_number(self, phone_number: str) -> Dict[str, Any]:
        """
        Release (delete) a purchased phone number
        
        Args:
            phone_number: The phone number to release
            
        Returns:
            Release result information
        """
        try:
            logger.info(f"Releasing phone number: {phone_number}")
            
            # Start release operation
            release_poller = self.client.begin_release_phone_number(phone_number)
            
            # Wait for release to complete
            release_result = release_poller.result()
            
            result = {
                "phone_number": phone_number,
                "status": "released",
                "message": "Phone number released successfully",
                "release_result": str(release_result) if release_result else None
            }
            
            logger.info(f"Successfully released phone number: {phone_number}")
            return result
            
        except HttpResponseError as e:
            logger.error(f"Failed to release phone number {phone_number}: {e}")
            return {
                "phone_number": phone_number,
                "status": "failed",
                "error": str(e),
                "message": "Failed to release phone number"
            }
        except Exception as e:
            logger.error(f"Unexpected error during phone number release: {e}")
            raise e


# Convenience functions for common operations
def purchase_random_phone_number(
    endpoint: str,
    country_code: str = "GB",
    toll_free: bool = True,
    calling_enabled: bool = True,
    sms_enabled: bool = True,
    credential: Optional[DefaultAzureCredential] = None
) -> Dict[str, Any]:
    """
    Convenience function to purchase a random phone number
    
    Args:
        endpoint: Azure Communication Services endpoint
        country_code: Country code for the phone number (2-letter ISO code)
        toll_free: Whether to purchase a toll-free number
        calling_enabled: Enable calling capability
        sms_enabled: Enable SMS capability
        credential: Azure credential
        
    Returns:
        Purchase result
    """
    manager = SimplePhoneNumberManager(endpoint, credential)
    request = PhoneNumberPurchaseRequest(
        country_code=country_code,
        toll_free=toll_free,
        calling_enabled=calling_enabled,
        sms_enabled=sms_enabled
    )
    return manager.purchase_random_phone_number(request)


def list_phone_numbers(
    endpoint: str,
    credential: Optional[DefaultAzureCredential] = None
) -> List[Dict[str, Any]]:
    """
    Convenience function to list purchased phone numbers
    
    Args:
        endpoint: Azure Communication Services endpoint
        credential: Azure credential
        
    Returns:
        List of purchased phone numbers
    """
    manager = SimplePhoneNumberManager(endpoint, credential)
    return manager.list_purchased_phone_numbers()
