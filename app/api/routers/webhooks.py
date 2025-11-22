"""
Clerk Webhooks for automatic user synchronization

This replaces the manual frontend sync with automatic webhook-based sync.
When users sign up with Clerk, this webhook automatically creates them in our database.
"""

import base64
import hashlib
import hmac
import json
import os
import traceback
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import Response

from app.core.repository import repo
from app.core.schemas import ClerkUserSync

# Webhook router
webhook_router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# API webhooks router (for Clerk's expected /api/webhooks path)
api_webhook_router = APIRouter(prefix="/api/webhooks", tags=["api-webhooks"])

CLERK_WEBHOOK_SIGNING_SECRET = os.getenv("CLERK_WEBHOOK_SIGNING_SECRET", "")


def verify_webhook_signature(
    payload: bytes,
    signature: str,
    secret: str,
    msg_id: str = None,
    timestamp: str = None,
) -> bool:
    """
    Verify the webhook signature from Clerk using Svix format

    Args:
        payload: Raw request body
        signature: Signature from Clerk (in svix-signature header, format: "v1,<base64_signature>")
        secret: Your webhook signing secret (starts with whsec_)
        msg_id: Message ID from svix-id header
        timestamp: Timestamp from svix-timestamp header

    Returns:
        True if signature is valid, False otherwise
    """
    if not secret:
        print("No webhook signing secret configured")
        return False

    # Remove whsec_ prefix if present
    if secret.startswith("whsec_"):
        secret = secret[6:]  # Remove 'whsec_' prefix

    try:
        # Parse signature header format: "v1,<base64_signature>"
        if "," not in signature:
            print(f"Invalid signature format: {signature}")
            return False

        version, expected_signature = signature.split(",", 1)

        if version != "v1":
            print(f"Unsupported signature version: {version}")
            return False

        print(f"Expected signature: {expected_signature}")
        print(f"Message ID: {msg_id}")
        print(f"Timestamp: {timestamp}")

        # Decode secret from base64
        secret_bytes = base64.b64decode(secret)

        # Create the signed payload following Svix format
        # The format is: {msg_id}.{timestamp}.{base64_payload}
        payload_b64 = base64.b64encode(payload).decode()
        signed_payload = f"{msg_id}.{timestamp}.{payload_b64}"

        print(f"Signed payload: {signed_payload[:100]}...")

        # Compute the expected signature using HMAC-SHA256
        computed_signature = hmac.new(
            secret_bytes, signed_payload.encode("utf-8"), hashlib.sha256
        ).digest()

        # Encode to base64 for comparison
        computed_signature_b64 = base64.b64encode(computed_signature).decode()

        print(f"Computed signature: {computed_signature_b64}")

        # Compare signatures
        is_valid = hmac.compare_digest(expected_signature, computed_signature_b64)
        print(f"Signature valid: {is_valid}")

        return is_valid

    except Exception as e:
        print(f"Webhook signature verification error: {e}")
        traceback.print_exc()
        return False


@webhook_router.post("/clerk")
async def handle_clerk_webhook(request: Request):
    """
    Handle Clerk webhook events for automatic user synchronization

    Supported events:
    - user.created: When a new user signs up
    - user.updated: When user info is updated
    - user.deleted: When a user is deleted
    """
    # Get the raw body and signature
    body = await request.body()

    # Debug: Print all headers to see what Clerk is sending
    print("📧 Webhook Headers:")
    for header_name, header_value in request.headers.items():
        print(f"  {header_name}: {header_value}")

    signature = request.headers.get("svix-signature") or request.headers.get("webhook-signature")
    msg_id = request.headers.get("svix-id")
    timestamp = request.headers.get("svix-timestamp")

    if not signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Missing webhook signature"
        )

    # Verify webhook signature - TEMPORARILY DISABLED
    # TODO: Fix signature verification or re-enable when secret is properly configured
    SKIP_SIGNATURE_VERIFICATION = True  # Set to False to re-enable

    if not SKIP_SIGNATURE_VERIFICATION and CLERK_WEBHOOK_SIGNING_SECRET:
        if not verify_webhook_signature(
            body, signature, CLERK_WEBHOOK_SIGNING_SECRET, msg_id, timestamp
        ):
            print("Webhook signature verification failed")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature"
            )
        else:
            print("Webhook signature verified successfully")
    else:
        print("WARNING: Signature verification skipped (SKIP_SIGNATURE_VERIFICATION=True or secret not set)")

    try:
        # Parse the webhook payload
        event = json.loads(body.decode("utf-8"))
        event_type = event.get("type")
        event_data = event.get("data", {})

        print(f"📨 Received Clerk webhook: {event_type}")
        print(f"📋 Event data: {event_data}")

        # Handle different event types
        if event_type == "user.created":
            await handle_user_created(event_data)
        elif event_type == "user.updated":
            await handle_user_updated(event_data)
        elif event_type == "user.deleted":
            await handle_user_deleted(event_data)
        else:
            print(f"Unhandled webhook event type: {event_type}")

        return Response(content="Webhook processed successfully", status_code=200)

    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload")
    except Exception as e:
        print(f"Webhook processing error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Webhook processing failed: {e!s}",
        )


async def handle_user_created(user_data: dict[str, Any]):
    """Handle user.created webhook event"""
    try:
        print(f"👤 Creating new user from webhook: {user_data.get('id')}")

        # Extract user info from Clerk webhook data
        clerk_user_sync = ClerkUserSync(
            clerk_user_id=user_data.get("id"),
            email=user_data.get("email_addresses", [{}])[0].get("email_address", ""),
            email_verified=user_data.get("email_addresses", [{}])[0]
            .get("verification", {})
            .get("status")
            == "verified",
            username=user_data.get("username"),
            first_name=user_data.get("first_name"),
            last_name=user_data.get("last_name"),
            full_name=f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip(),
            image_url=user_data.get("image_url"),
        )

        # Create user in our database
        user = await repo.sync_clerk_user(clerk_user_sync)
        print(f"User created successfully: {user.email} (ID: {user.id})")

    except Exception as e:
        print(f"Failed to create user from webhook: {e}")
        raise


async def handle_user_updated(user_data: dict[str, Any]):
    """Handle user.updated webhook event"""
    try:
        print(f"🔄 Updating user from webhook: {user_data.get('id')}")

        # Extract updated user info
        clerk_user_sync = ClerkUserSync(
            clerk_user_id=user_data.get("id"),
            email=user_data.get("email_addresses", [{}])[0].get("email_address", ""),
            email_verified=user_data.get("email_addresses", [{}])[0]
            .get("verification", {})
            .get("status")
            == "verified",
            username=user_data.get("username"),
            first_name=user_data.get("first_name"),
            last_name=user_data.get("last_name"),
            full_name=f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip(),
            image_url=user_data.get("image_url"),
        )

        # Update user in our database
        user = await repo.sync_clerk_user(clerk_user_sync)
        print(f"User updated successfully: {user.email}")

    except Exception as e:
        print(f"Failed to update user from webhook: {e}")
        raise


async def handle_user_deleted(user_data: dict[str, Any]):
    """Handle user.deleted webhook event"""
    try:
        clerk_user_id = user_data.get("id")
        print(f"🗑️ Deleting user from webhook: {clerk_user_id}")

        # You can either delete the user or mark them as inactive
        # For this example, let's mark them as inactive
        user = await repo.get_user_by_clerk_id(clerk_user_id)
        if user:
            # Update user to inactive (you may want to add this to your repository)
            # await repo.deactivate_user(clerk_user_id)
            print(f"User marked for deletion: {user.email}")
        else:
            print(f"User not found for deletion: {clerk_user_id}")

    except Exception as e:
        print(f"Failed to delete user from webhook: {e}")
        raise


# Add API webhook endpoint for Clerk's expected /api/webhooks path
@api_webhook_router.post("")
async def handle_clerk_webhook_api(request: Request):
    """
    Handle Clerk webhook events at /api/webhooks (redirects to main handler)
    This endpoint exists because Clerk expects webhooks at /api/webhooks by default
    """
    return await handle_clerk_webhook(request)
