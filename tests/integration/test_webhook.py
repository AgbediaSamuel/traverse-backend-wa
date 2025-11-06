#!/usr/bin/env python3
"""
Test the Clerk webhook endpoint

This simulates what Clerk sends when a user signs up
"""

import hashlib
import hmac
import json

import requests

# Test webhook payload (simulates Clerk user.created event)
test_payload = {
    "type": "user.created",
    "data": {
        "id": "user_webhook_test_123",
        "email_addresses": [
            {
                "email_address": "webhook.test@example.com",
                "verification": {"status": "verified"},
            }
        ],
        "username": "webhooktest",
        "first_name": "Webhook",
        "last_name": "Test",
        "image_url": "https://images.clerk.dev/test.jpg",
    },
}


def create_test_signature(payload: str, secret: str) -> str:
    """Create a test signature for webhook verification"""
    signature = hmac.new(
        secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return f"v1={signature}"


def test_webhook():
    """Test the webhook endpoint"""
    url = "http://localhost:8000/webhooks/clerk"
    payload_str = json.dumps(test_payload)

    # Use a test secret (replace with your actual webhook secret)
    test_secret = "test_secret_123"
    signature = create_test_signature(payload_str, test_secret)

    headers = {"Content-Type": "application/json", "svix-signature": signature}

    print("Testing Clerk webhook endpoint...")
    print(f"URL: {url}")
    print(f"Payload: {payload_str}")
    print(f"Signature: {signature}")

    try:
        response = requests.post(url, data=payload_str, headers=headers)

        print(f"Response Status: {response.status_code}")
        print(f"Response Body: {response.text}")

        if response.status_code == 200:
            print("Webhook test successful")
        else:
            print("Webhook test failed")

    except requests.exceptions.ConnectionError:
        print("Cannot connect to backend - make sure it's running on port 8000")
    except Exception as e:
        print(f"Test error: {e}")


if __name__ == "__main__":
    test_webhook()
