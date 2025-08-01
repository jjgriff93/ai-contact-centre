#!/usr/bin/env python3
"""
Simple CLI for Azure Communication Services Phone Number Management

This script provides a simple command-line interface for managing phone numbers.
"""

import sys
import os
from pathlib import Path

# Load environment variables from .env file if present
env_file = Path(__file__).parent / '.env'
if env_file.exists():
    with open(env_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                if key not in os.environ:  # Don't override existing env vars
                    os.environ[key] = value

# Configuration - uses the same environment variables as the main application
def get_acs_endpoint():
    """Get ACS endpoint from environment variables, handling both formats"""
    # Try AZURE_ACS_ENDPOINT first (used by main app)
    azure_acs_endpoint = os.getenv("AZURE_ACS_ENDPOINT")
    if azure_acs_endpoint:
        return azure_acs_endpoint.rstrip('/')
    
    # Try ACS_ENDPOINT (connection string format)
    acs_endpoint = os.getenv("ACS_ENDPOINT")
    if acs_endpoint and "endpoint=" in acs_endpoint:
        # Extract endpoint URL from connection string
        endpoint_part = acs_endpoint.split("endpoint=")[1].split(";")[0]
        return endpoint_part.rstrip('/')
    
    # Fallback - try to extract resource name from connection string for backward compatibility
    if acs_endpoint:
        return acs_endpoint.rstrip('/')
    
    # Last resort fallback
    return "https://acs-3iihfyj43p7c4.communication.azure.com"

def get_acs_resource_name():
    """Extract ACS resource name from endpoint"""
    endpoint = get_acs_endpoint()
    try:
        # Extract resource name from URL like https://acs-xyz.communication.azure.com
        if "://" in endpoint:
            hostname = endpoint.split("://")[1].split("/")[0]
            if ".communication.azure.com" in hostname:
                return hostname.split(".communication.azure.com")[0]
    except Exception:
        pass
    return "acs-resource"

ACS_ENDPOINT = get_acs_endpoint()
ACS_RESOURCE_NAME = get_acs_resource_name()


def validate_phone_number(phone_number: str) -> bool:
    """Validate phone number format"""
    if not phone_number:
        return False
    
    # Basic validation - should start with + and contain only digits and + 
    if not phone_number.startswith('+'):
        return False
    
    # Remove + and check if remaining are digits
    digits_only = phone_number[1:].replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
    if not digits_only.isdigit():
        return False
    
    # Check reasonable length (7-15 digits is standard for international numbers)
    if len(digits_only) < 7 or len(digits_only) > 15:
        return False
    
    return True


def validate_country_code(country: str) -> bool:
    """Validate country code against supported countries"""
    try:
        from phone_manager import CountryCode
        return country.upper() in [code.value for code in CountryCode]
    except Exception:
        # Fallback list of common countries
        supported = ['US', 'CA', 'GB', 'AU', 'FR', 'DE', 'IT', 'ES', 'NL', 'SE', 'NO', 'DK', 'FI', 'IE', 'CH', 'AT', 'BE', 'PT']
        return country.upper() in supported


def list_numbers():
    """List all purchased phone numbers"""
    try:
        from phone_manager import list_phone_numbers_sync
        
        print(f"📱 Listing phone numbers for {ACS_RESOURCE_NAME}...")
        numbers = list_phone_numbers_sync(ACS_ENDPOINT)
        
        if not numbers:
            print("No phone numbers currently owned")
            return
        
        print(f"Found {len(numbers)} phone numbers:")
        for i, number in enumerate(numbers, 1):
            print(f"\n{i}. {number['phone_number']}")
            print(f"   Country: {number['country_code']}")
            print(f"   Type: {number['phone_number_type']}")
            print(f"   Capabilities: {number['capabilities']}")
            if number.get('cost'):
                print(f"   Cost: {number['cost']} {number['currency']}")
        
    except Exception as e:
        print(f"❌ Error listing phone numbers: {e}")


def search_numbers(country="US", toll_free=True):
    """Search for available phone numbers"""
    try:
        # Validate country code
        if not validate_country_code(country):
            print(f"❌ Unsupported country code: {country}")
            print("Supported countries: US, CA, GB, AU, FR, DE, IT, ES, NL, SE, NO, DK, FI, IE, CH, AT, BE, PT")
            return []
        
        from phone_manager import SimplePhoneNumberManager, PhoneNumberPurchaseRequest, CountryCode
        
        print(f"🔍 Searching for {country} {'toll-free' if toll_free else 'geographic'} numbers...")
        
        manager = SimplePhoneNumberManager(ACS_ENDPOINT)
        request = PhoneNumberPurchaseRequest(
            country_code=CountryCode(country),
            toll_free=toll_free,
            quantity=1,
            calling_enabled=True,
            sms_enabled=False  # Disable SMS for better compatibility
        )
        
        results = manager.search_available_phone_numbers(request)
        
        if not results:
            print("No available phone numbers found")
            return []
        
        print(f"Found {len(results)} available phone numbers:")
        for i, result in enumerate(results, 1):
            print(f"\n{i}. {result.phone_number}")
            print(f"   Type: {result.phone_number_type}")
            print(f"   Capabilities: {result.capabilities}")
            if result.cost:
                print(f"   Cost: {result.cost} {result.currency}")
        
        return results
        
    except Exception as e:
        print(f"❌ Error searching phone numbers: {e}")
        return []


def purchase_number(country, toll_free, specific_number=None):
    """Purchase a phone number (specific or random)"""
    try:
        # Validate country code
        if not validate_country_code(country):
            print(f"❌ Unsupported country code: {country}")
            print("Supported countries: US, CA, GB, AU, FR, DE, IT, ES, NL, SE, NO, DK, FI, IE, CH, AT, BE, PT")
            return
        
        # Validate specific phone number if provided
        if specific_number and not validate_phone_number(specific_number):
            print(f"❌ Invalid phone number format: {specific_number}")
            print("Phone number should start with + and contain 7-15 digits")
            return
        
        from phone_manager import purchase_random_phone_number_sync, CountryCode, SimplePhoneNumberManager, PhoneNumberPurchaseRequest
        
        if specific_number:
            print(f"💰 Purchasing specific number: {specific_number}")
        else:
            print(f"💰 Purchasing {country} {'toll-free' if toll_free else 'geographic'} number...")
        
        print("⚠️  This will incur charges to your Azure account!")
        
        confirm = input("Are you sure you want to proceed? (yes/no): ").strip().lower()
        if confirm not in ['yes', 'y']:
            print("Purchase cancelled")
            return

        if specific_number:
            # Purchase specific number by searching for it first
            manager = SimplePhoneNumberManager(ACS_ENDPOINT)
            request = PhoneNumberPurchaseRequest(
                country_code=CountryCode(country),
                toll_free=toll_free,
                calling_enabled=True,
                sms_enabled=False
            )
            
            # Search for available numbers
            available_numbers = manager.search_available_phone_numbers(request)
            
            # Find the specific number in the search results
            target_number = None
            for num in available_numbers:
                if num.phone_number == specific_number:
                    target_number = num
                    break
            
            if not target_number:
                print(f"❌ Specific number {specific_number} not found in available numbers")
                print("Available numbers:")
                for num in available_numbers:
                    print(f"   - {num.phone_number} (Cost: {num.cost} {num.currency})")
                return
            
            # Purchase using the search ID
            result = manager.purchase_phone_number_by_search_id(target_number.search_id)
            
            if result.get('status') == 'purchased':
                print("✅ Purchase successful!")
                print(f"   Phone Number: {specific_number}")
                print(f"   Search ID: {result.get('search_id')}")
                print(f"   Cost: {target_number.cost} {target_number.currency}")
            else:
                print(f"❌ Purchase failed: {result.get('message')}")
        
        else:
            # Random purchase (existing logic)
            result = purchase_random_phone_number_sync(
                endpoint=ACS_ENDPOINT,
                country_code=CountryCode(country),
                toll_free=toll_free,
                calling_enabled=True,
                sms_enabled=False  # Disable SMS for better compatibility
            )
            
            if result.get('status') == 'purchased':
                print("✅ Purchase successful!")
                print(f"   Search ID: {result.get('search_id')}")
                print(f"   Available numbers found: {result.get('available_numbers', 0)}")
                
                if 'searched_numbers' in result:
                    print("   Numbers purchased:")
                    for num in result['searched_numbers']:
                        print(f"   - {num['phone_number']}")
                        if num.get('cost'):
                            print(f"     Cost: {num['cost']} {num['currency']}")
            else:
                print(f"❌ Purchase failed: {result.get('message')}")
        
    except Exception as e:
        print(f"❌ Error purchasing phone number: {e}")


def release_number(phone_number):
    """Release a phone number"""
    try:
        # Validate phone number format
        if not validate_phone_number(phone_number):
            print(f"❌ Invalid phone number format: {phone_number}")
            print("Phone number should start with + and contain 7-15 digits")
            return
        
        from phone_manager import SimplePhoneNumberManager
        
        print(f"🗑️  Releasing phone number: {phone_number}")
        
        confirm = input(f"Are you sure you want to release {phone_number}? (yes/no): ").strip().lower()
        if confirm not in ['yes', 'y']:
            print("Release cancelled")
            return
        
        manager = SimplePhoneNumberManager(ACS_ENDPOINT)
        result = manager.release_phone_number(phone_number)
        
        if result.get('status') == 'released':
            print(f"✅ Successfully released {phone_number}")
        else:
            print(f"❌ Failed to release {phone_number}: {result.get('message')}")
        
    except Exception as e:
        print(f"❌ Error releasing phone number: {e}")


def main():
    """Main CLI function"""
    print("=" * 60)
    print("Azure Communication Services Phone Number Management")
    print("Simple CLI Tool")
    print("=" * 60)
    print(f"ACS Resource: {ACS_RESOURCE_NAME}")
    print(f"Endpoint: {ACS_ENDPOINT}")
    print("=" * 60)
    
    if len(sys.argv) < 2 or sys.argv[1] in ['--help', '-h', 'help']:
        print("📋 Usage:")
        print("  python phone_cli.py list                              # List owned numbers")
        print("  python phone_cli.py search [country] [type]           # Search available numbers")
        print("  python phone_cli.py purchase [country] [type] [number] # Purchase a phone number")
        print("  python phone_cli.py release <phone_number>            # Release a number")
        print()
        print("Examples:")
        print("  python phone_cli.py list")
        print("  python phone_cli.py search US toll-free")
        print("  python phone_cli.py search GB")
        print("  python phone_cli.py purchase")
        print("  python phone_cli.py purchase US toll-free")
        print("  python phone_cli.py purchase GB geographic")
        print("  python phone_cli.py purchase US toll-free +18001234567")
        print("  python phone_cli.py release +1234567890")
        return
    
    command = sys.argv[1].lower()
    
    if command == 'list':
        list_numbers()
        
    elif command == 'search':
        country = sys.argv[2].upper() if len(sys.argv) > 2 else "US"
        number_type = sys.argv[3].lower() if len(sys.argv) > 3 else "toll-free"
        
        if number_type not in ['toll-free', 'geographic']:
            print(f"❌ Invalid number type: {number_type}")
            print("Valid types: toll-free, geographic")
            return
        
        toll_free = number_type == "toll-free"
        search_numbers(country, toll_free)
        
    elif command == 'purchase':
        country = sys.argv[2].upper() if len(sys.argv) > 2 else "US"
        number_type = sys.argv[3].lower() if len(sys.argv) > 3 else "toll-free"
        
        if number_type not in ['toll-free', 'geographic']:
            print(f"❌ Invalid number type: {number_type}")
            print("Valid types: toll-free, geographic")
            return
        
        toll_free = number_type == "toll-free"
        specific_number = sys.argv[4] if len(sys.argv) > 4 else None
        purchase_number(country, toll_free, specific_number)
        
    elif command == 'release':
        if len(sys.argv) < 3:
            print("❌ Phone number required for release command")
            print("Usage: python phone_cli.py release <phone_number>")
            return
        phone_number = sys.argv[2]
        release_number(phone_number)
        
    else:
        print(f"❌ Unknown command: {command}")
        print("Available commands: list, search, purchase, release")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n❌ Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)
