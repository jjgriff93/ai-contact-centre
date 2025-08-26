#!/usr/bin/env python3
"""
Simple CLI for Azure Communication Services Phone Number Management

This script provides a simple command-line interface for managing phone numbers.
"""

import sys
import os
from pathlib import Path

# Load environment variables from azd when available
try:
    from dotenv_azd import load_azd_env
    load_azd_env()
    print("✅ Loaded environment from azd")
except ImportError:
    print("⚠️ dotenv-azd not available. Ensure environment variables are set manually.")
    print("   You can install it with: uv add dotenv-azd")
except Exception as e:
    print(f"⚠️ Could not load azd environment: {e}")
    print("   Make sure you've run 'azd up' or 'azd env select' first.")

# Configuration - uses the same environment variables as the main application
def get_acs_endpoint():
    """Get ACS endpoint from environment variables, handling both formats"""
    # Try AZURE_ACS_ENDPOINT first (used by main app)
    azure_acs_endpoint = os.getenv("AZURE_ACS_ENDPOINT")
    if azure_acs_endpoint:
        endpoint = azure_acs_endpoint.rstrip('/')
        # Add https:// prefix if missing
        if not endpoint.startswith('http'):
            endpoint = f"https://{endpoint}"
        return endpoint
    
    # Try ACS_ENDPOINT (connection string format)
    acs_endpoint = os.getenv("ACS_ENDPOINT")
    if acs_endpoint and "endpoint=" in acs_endpoint:
        # Extract endpoint URL from connection string
        endpoint_part = acs_endpoint.split("endpoint=")[1].split(";")[0]
        return endpoint_part.rstrip('/')
    
    # Fallback - try to extract resource name from connection string for backward compatibility
    if acs_endpoint:
        endpoint = acs_endpoint.rstrip('/')
        # Add https:// prefix if missing
        if not endpoint.startswith('http'):
            endpoint = f"https://{endpoint}"
        return endpoint
    
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


def purchase_number(country, toll_free, specific_number=None, auto_confirm=False):
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
        
        if not auto_confirm:
            confirm = input("Are you sure you want to proceed? (yes/no): ").strip().lower()
            if confirm not in ['yes', 'y']:
                print("Purchase cancelled")
                return
        else:
            print("Auto-confirming purchase...")

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


def ensure_number(country, toll_free, auto_confirm=False):
    """Ensure exactly one phone number exists with the specified configuration (idempotent)"""
    try:
        # Validate country code
        if not validate_country_code(country):
            print(f"❌ Unsupported country code: {country}")
            print("Supported countries: US, CA, GB, AU, FR, DE, IT, ES, NL, SE, NO, DK, FI, IE, CH, AT, BE, PT")
            return
        
        from phone_manager import list_phone_numbers_sync, SimplePhoneNumberManager
        
        number_type_str = 'toll-free' if toll_free else 'geographic'
        print(f"🔄 Ensuring {country} {number_type_str} phone number...")
        
        # Get current phone numbers
        numbers = list_phone_numbers_sync(ACS_ENDPOINT)
        
        # Find numbers that match the desired configuration
        matching_numbers = []
        non_matching_numbers = []
        
        for number in numbers:
            # Check if number matches desired configuration
            is_toll_free = number['phone_number_type'].lower() in ['tollfree', 'toll-free', 'toll_free']
            is_geographic = number['phone_number_type'].lower() in ['geographic', 'local']
            
            number_matches_type = (toll_free and is_toll_free) or (not toll_free and is_geographic)
            number_matches_country = number['country_code'].upper() == country.upper()
            
            if number_matches_type and number_matches_country:
                matching_numbers.append(number)
            else:
                non_matching_numbers.append(number)
        
        print(f"📊 Found {len(numbers)} total phone numbers:")
        print(f"   - {len(matching_numbers)} matching {country} {number_type_str}")
        print(f"   - {len(non_matching_numbers)} not matching configuration")
        
        # Release non-matching numbers
        if non_matching_numbers:
            print(f"\n🗑️  Releasing {len(non_matching_numbers)} non-matching numbers...")
            manager = SimplePhoneNumberManager(ACS_ENDPOINT)
            
            for number in non_matching_numbers:
                phone_number = number['phone_number']
                number_type = number['phone_number_type']
                country_code = number['country_code']
                
                if not auto_confirm:
                    confirm = input(f"Release {phone_number} ({country_code} {number_type})? (yes/no): ").strip().lower()
                    if confirm not in ['yes', 'y']:
                        print(f"   Skipped: {phone_number}")
                        continue
                
                try:
                    result = manager.release_phone_number(phone_number)
                    if result.get('status') == 'released':
                        print(f"   ✅ Released: {phone_number}")
                    else:
                        print(f"   ❌ Failed to release {phone_number}: {result.get('message')}")
                except Exception as e:
                    print(f"   ❌ Error releasing {phone_number}: {e}")
        
        # Ensure exactly one matching number exists
        if len(matching_numbers) == 0:
            print(f"\n💰 No matching number found. Purchasing {country} {number_type_str} number...")
            purchase_number(country, toll_free, None, auto_confirm)
        elif len(matching_numbers) == 1:
            number = matching_numbers[0]
            print(f"\n✅ Found existing matching number: {number['phone_number']}")
            print(f"   Country: {number['country_code']}")
            print(f"   Type: {number['phone_number_type']}")
            print(f"   Capabilities: {number['capabilities']}")
        else:
            # Multiple matching numbers - keep the first one, release the rest
            keep_number = matching_numbers[0]
            release_numbers = matching_numbers[1:]
            
            print(f"\n📍 Found {len(matching_numbers)} matching numbers. Keeping: {keep_number['phone_number']}")
            
            if release_numbers and not auto_confirm:
                confirm = input(f"Release {len(release_numbers)} extra matching numbers? (yes/no): ").strip().lower()
                if confirm not in ['yes', 'y']:
                    print("   Skipped releasing extra numbers")
                    return
            
            manager = SimplePhoneNumberManager(ACS_ENDPOINT)
            for number in release_numbers:
                phone_number = number['phone_number']
                try:
                    result = manager.release_phone_number(phone_number)
                    if result.get('status') == 'released':
                        print(f"   ✅ Released extra: {phone_number}")
                    else:
                        print(f"   ❌ Failed to release {phone_number}: {result.get('message')}")
                except Exception as e:
                    print(f"   ❌ Error releasing {phone_number}: {e}")
        
    except Exception as e:
        print(f"❌ Error ensuring phone number: {e}")


def main():
    """Main CLI function"""
    print("=" * 60)
    print("Azure Communication Services Phone Number Management")
    print("Simple CLI Tool")
    print("=" * 60)
    print(f"ACS Resource: {ACS_RESOURCE_NAME}")
    print(f"Endpoint: {ACS_ENDPOINT}")
    print("=" * 60)
    
    # Check for --yes flag
    auto_confirm = '--yes' in sys.argv or '-y' in sys.argv
    if auto_confirm:
        # Remove --yes or -y from argv for simpler parsing
        sys.argv = [arg for arg in sys.argv if arg not in ['--yes', '-y']]
    
    if len(sys.argv) < 2 or sys.argv[1] in ['--help', '-h', 'help']:
        print("📋 Usage:")
        print("  python phone_cli.py list                              # List owned numbers")
        print("  python phone_cli.py search [country] [type]           # Search available numbers")
        print("  python phone_cli.py purchase [country] [type] [number] [--yes] # Purchase a phone number")
        print("  python phone_cli.py ensure [country] [type] [--yes]    # Ensure exactly one number exists (idempotent)")
        print("  python phone_cli.py release <phone_number>            # Release a number")
        print()
        print("Options:")
        print("  --yes, -y    Auto-confirm purchase/release (skip confirmation prompts)")
        print()
        print("Examples:")
        print("  python phone_cli.py list")
        print("  python phone_cli.py search US toll-free")
        print("  python phone_cli.py search GB")
        print("  python phone_cli.py purchase")
        print("  python phone_cli.py purchase US toll-free")
        print("  python phone_cli.py purchase GB toll-free --yes")
        print("  python phone_cli.py ensure GB toll-free --yes          # Idempotent deployment")
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
        purchase_number(country, toll_free, specific_number, auto_confirm)
        
    elif command == 'ensure':
        country = sys.argv[2].upper() if len(sys.argv) > 2 else "GB"
        number_type = sys.argv[3].lower() if len(sys.argv) > 3 else "toll-free"
        
        if number_type not in ['toll-free', 'geographic']:
            print(f"❌ Invalid number type: {number_type}")
            print("Valid types: toll-free, geographic")
            return
        
        toll_free = number_type == "toll-free"
        ensure_number(country, toll_free, auto_confirm)
        
    elif command == 'release':
        if len(sys.argv) < 3:
            print("❌ Phone number required for release command")
            print("Usage: python phone_cli.py release <phone_number>")
            return
        phone_number = sys.argv[2]
        release_number(phone_number)
        
    else:
        print(f"❌ Unknown command: {command}")
        print("Available commands: list, search, purchase, ensure, release")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n❌ Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)