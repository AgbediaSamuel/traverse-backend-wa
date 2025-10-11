#!/usr/bin/env python3
"""
Test script for clerk_auth.py

This script tests the ClerkAuth class functionality including:
- Environment variable loading
- Token verification (with mock tokens)
- User data extraction
- Clerk API integration

Run this from the backend root directory:
cd /Users/fdeclan/Public/traverse/traverse-backend-wa
python3 test_clerk_auth.py
"""

import asyncio
import os
import sys

from dotenv import load_dotenv

# Add the app directory to Python path when running as a script
repo_root = os.path.dirname(os.path.abspath(__file__))
if os.path.basename(repo_root) not in {"tests", "unit", "integration"}:
    sys.path.append(os.path.join(repo_root, "app"))

# Load environment variables
load_dotenv()

from app.core.clerk_auth import CLERK_JWT_KEY, CLERK_SECRET_KEY, ClerkAuth, clerk_auth


def test_environment_variables():
    """Test if environment variables are loaded correctly"""
    print("Testing Environment Variables...")
    print(f"CLERK_SECRET_KEY: {'Set' if CLERK_SECRET_KEY else 'Missing'}")
    print(f"CLERK_JWT_KEY: {'Set' if CLERK_JWT_KEY else 'Missing'}")

    if CLERK_SECRET_KEY:
        print(f"   Secret key preview: {CLERK_SECRET_KEY[:20]}...")
    if CLERK_JWT_KEY:
        print(f"   JWT key preview: {CLERK_JWT_KEY[:50]}...")

    print()


def test_clerk_auth_initialization():
    """Test ClerkAuth class initialization"""
    print("Testing ClerkAuth Initialization...")

    try:
        auth = ClerkAuth()
        print("ClerkAuth initialized successfully")
        return auth
    except Exception as e:
        print(f"ClerkAuth initialization failed: {e}")
        return None


def create_mock_jwt_payload():
    """Create a mock JWT payload that simulates Clerk token data"""
    return {
        "sub": "user_2abcdefghijklmnop",  # Clerk user ID
        "email": "test.user@example.com",
        "email_verified": True,
        "username": "testuser123",
        "given_name": "Test",
        "family_name": "User",
        "picture": "https://images.clerk.dev/uploaded/img_test.jpg",
        "iat": 1696800000,  # Issued at timestamp
        "exp": 1696803600,  # Expiration timestamp
        "iss": "https://clerk.dev",
        "aud": "test-audience",
    }


def test_user_data_extraction():
    """Test user data extraction from mock Clerk payload"""
    print("Testing User Data Extraction...")

    if not clerk_auth:
        print("Cannot test - ClerkAuth not initialized")
        return

    mock_payload = create_mock_jwt_payload()
    print(f"Mock Clerk payload: {mock_payload}")

    try:
        user_data = clerk_auth.extract_user_data(mock_payload)
        print("User data extraction successful")
        print("Extracted user data:")
        for key, value in user_data.items():
            print(f"   {key}: {value}")
        return user_data
    except Exception as e:
        print(f"User data extraction failed: {e}")
        return None


async def test_token_verification():
    """Test JWT token verification with mock token"""
    print("Testing Token Verification...")

    if not clerk_auth:
        print("Cannot test - ClerkAuth not initialized")
        return

    # Create a mock JWT token (this is just for testing the decode logic)
    # In real usage, this would come from Clerk's frontend
    mock_token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1c2VyXzJhYmNkZWZnaGlqa2xtbm9wIiwiZW1haWwiOiJ0ZXN0LnVzZXJAZXhhbXBsZS5jb20iLCJlbWFpbF92ZXJpZmllZCI6dHJ1ZSwidXNlcm5hbWUiOiJ0ZXN0dXNlcjEyMyIsImdpdmVuX25hbWUiOiJUZXN0IiwiZmFtaWx5X25hbWUiOiJVc2VyIiwicGljdHVyZSI6Imh0dHBzOi8vaW1hZ2VzLmNsZXJrLmRldi91cGxvYWRlZC9pbWdfdGVzdC5qcGciLCJpYXQiOjE2OTY4MDAwMDAsImV4cCI6MTY5NjgwMzYwMCwiaXNzIjoiaHR0cHM6Ly9jbGVyay5kZXYiLCJhdWQiOiJ0ZXN0LWF1ZGllbmNlIn0.mock_signature"

    try:
        print(f"Testing with mock token: {mock_token[:50]}...")
        result = await clerk_auth.verify_clerk_token(mock_token)

        if result:
            print("Token verification successful")
            print("Decoded token data:")
            for key, value in result.items():
                print(f"   {key}: {value}")
        else:
            print("Token verification failed - returned None")

        return result
    except Exception as e:
        print(f"Token verification error: {e}")
        return None


async def test_clerk_api_call():
    """Test Clerk API call (this will likely fail without valid credentials)"""
    print("Testing Clerk API Call...")

    if not clerk_auth:
        print("Cannot test - ClerkAuth not initialized")
        return

    if not CLERK_SECRET_KEY or CLERK_SECRET_KEY == "your_clerk_secret_key_here":
        print("Skipping API test - no valid Clerk secret key")
        return

    # Use a mock user ID for testing
    test_user_id = "user_2abcdefghijklmnop"

    try:
        print(f"Fetching user info for: {test_user_id}")
        user_info = await clerk_auth.get_clerk_user_info(test_user_id)

        if user_info:
            print("Clerk API call successful")
            print(f"User info: {user_info}")
        else:
            print("Clerk API call failed - returned None")

        return user_info
    except Exception as e:
        print(f"Clerk API call error: {e}")
        return None


async def main():
    """Run all tests"""
    print("Starting ClerkAuth Tests\n")
    print("=" * 50)

    # Test 1: Environment Variables
    test_environment_variables()

    # Test 2: Initialization
    auth = test_clerk_auth_initialization()
    print()

    # Test 3: User Data Extraction
    user_data = test_user_data_extraction()
    print()

    # Test 4: Token Verification
    token_result = await test_token_verification()
    print()

    # Test 5: Clerk API Call
    api_result = await test_clerk_api_call()
    print()

    # Summary
    print("=" * 50)
    print("Test Summary:")
    print(f"Environment Variables: {'OK' if CLERK_SECRET_KEY else 'Missing'}")
    print(f"Initialization: {'OK' if auth else 'Failed'}")
    print(f"Data Extraction: {'OK' if user_data else 'Failed'}")
    print(f"Token Verification: {'OK' if token_result else 'Failed'}")
    print(f"API Call: {'OK' if api_result else 'Skipped/Failed'}")

    if auth and user_data and token_result:
        print("\nClerkAuth is working correctly")
    else:
        print("\nSome tests failed - check your configuration")


if __name__ == "__main__":
    asyncio.run(main())
