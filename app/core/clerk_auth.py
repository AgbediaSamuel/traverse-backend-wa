import os
from typing import Any

import httpx
from jose import JWTError, jwt

# Clerk configuration
CLERK_SECRET_KEY = os.getenv("CLERK_SECRET_KEY")
print(CLERK_SECRET_KEY)
CLERK_JWT_KEY = os.getenv("CLERK_JWT_KEY")


class ClerkAuth:
    """Clerk authentication helper class"""

    def __init__(self):
        if not CLERK_SECRET_KEY:
            raise ValueError("CLERK_SECRET_KEY environment variable is required")

    async def verify_clerk_token(self, token: str) -> dict[str, Any] | None:
        """
        Verify a Clerk JWT token and return user information

        Args:
            token: The Clerk JWT token to verify

        Returns:
            Dict with user information if valid, None if invalid
        """
        try:
            # Remove 'Bearer ' prefix if present
            if token.startswith("Bearer "):
                token = token[7:]

            # Decode the JWT token without verification first to get the header
            unverified_header = jwt.get_unverified_header(token)

            # For development, we'll decode without verification
            # In production, you should verify against Clerk's public keys
            payload = jwt.decode(
                token,
                options={
                    "verify_signature": False
                },  # Skip signature verification for now
            )

            return payload

        except JWTError as e:
            print(f"JWT Error: {e}")
            return None
        except Exception as e:
            print(f"Token verification error: {e}")
            return None

    async def get_clerk_user_info(self, user_id: str) -> dict[str, Any] | None:
        """
        Fetch user information from Clerk API

        Args:
            user_id: Clerk user ID

        Returns:
            User information from Clerk API
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://api.clerk.dev/v1/users/{user_id}",
                    headers={
                        "Authorization": f"Bearer {CLERK_SECRET_KEY}",
                        "Content-Type": "application/json",
                    },
                )

                if response.status_code == 200:
                    return response.json()
                else:
                    print(f"Clerk API error: {response.status_code} - {response.text}")
                    return None

        except Exception as e:
            print(f"Error fetching user from Clerk: {e}")
            return None

    def extract_user_data(self, clerk_payload: dict[str, Any]) -> dict[str, Any]:
        """
        Extract standardized user data from Clerk token payload

        Args:
            clerk_payload: The decoded Clerk JWT payload

        Returns:
            Standardized user data dictionary
        """
        # Extract common fields from Clerk token
        return {
            "clerk_user_id": clerk_payload.get("sub"),  # Clerk user ID
            "email": clerk_payload.get("email"),
            "email_verified": clerk_payload.get("email_verified", False),
            "username": clerk_payload.get("username"),
            "first_name": clerk_payload.get("given_name"),
            "last_name": clerk_payload.get("family_name"),
            "full_name": f"{clerk_payload.get('given_name', '')} {clerk_payload.get('family_name', '')}".strip(),
            "image_url": clerk_payload.get("picture"),
            "created_at": clerk_payload.get("iat"),  # Issued at time
        }


# Global Clerk auth instance
clerk_auth = ClerkAuth()
