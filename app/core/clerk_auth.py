import logging
import os
from typing import Any

import httpx
from jose import JWTError, jwt

logger = logging.getLogger(__name__)

# Clerk configuration
CLERK_SECRET_KEY = os.getenv("CLERK_SECRET_KEY")
CLERK_PUBLISHABLE_KEY = os.getenv("CLERK_PUBLISHABLE_KEY", "")

# Cache for Clerk's public keys
_clerk_jwks_cache: dict[str, Any] | None = None


class ClerkAuth:
    """Clerk authentication helper class"""

    def __init__(self):
        if not CLERK_SECRET_KEY:
            raise ValueError("CLERK_SECRET_KEY environment variable is required")

    async def _get_clerk_jwks(self) -> dict[str, Any] | None:
        """
        Fetch Clerk's JWKS (JSON Web Key Set) for JWT verification.

        Returns:
            JWKS dictionary with public keys
        """
        global _clerk_jwks_cache

        # Use cache if available
        if _clerk_jwks_cache:
            return _clerk_jwks_cache

        try:
            # Clerk publishable keys don't contain domain info directly
            # For JWKS, we need to use Clerk's instance URL
            # In development, we'll skip JWKS verification and use dev mode fallback
            # In production, you should set CLERK_INSTANCE_URL or CLERK_JWKS_URL

            jwks_url = None

            # Try to get JWKS URL from environment variable first
            clerk_jwks_url = os.getenv("CLERK_JWKS_URL")
            if clerk_jwks_url:
                jwks_url = clerk_jwks_url
            else:
                # Try to construct from instance URL if available
                clerk_instance_url = os.getenv("CLERK_INSTANCE_URL")
                if clerk_instance_url:
                    # Remove trailing slash if present
                    instance_url = clerk_instance_url.rstrip("/")
                    jwks_url = f"{instance_url}/.well-known/jwks.json"
                elif CLERK_PUBLISHABLE_KEY:
                    # Try to extract instance from publishable key
                    # Format: pk_test_<instance-id> or pk_live_<instance-id>
                    # But this doesn't give us the full domain
                    # For now, skip JWKS in dev mode (we'll use unverified decoding)
                    is_dev = (
                        os.getenv("ENVIRONMENT", "development").lower() == "development"
                    )
                    if is_dev:
                        logger.debug(
                            "Development mode: Skipping JWKS verification. "
                            "Set CLERK_JWKS_URL or CLERK_INSTANCE_URL for production."
                        )
                        return None
                    else:
                        logger.warning(
                            "Cannot construct JWKS URL from publishable key. "
                            "Set CLERK_JWKS_URL or CLERK_INSTANCE_URL environment variable."
                        )
                        return None
                else:
                    # No publishable key - can't verify JWKS
                    is_dev = (
                        os.getenv("ENVIRONMENT", "development").lower() == "development"
                    )
                    if is_dev:
                        logger.debug(
                            "Development mode: No CLERK_PUBLISHABLE_KEY set, skipping JWKS verification"
                        )
                    else:
                        logger.warning(
                            "No CLERK_PUBLISHABLE_KEY set, skipping JWKS verification"
                        )
                    return None

            if not jwks_url:
                return None

            async with httpx.AsyncClient() as client:
                response = await client.get(jwks_url, timeout=5.0)
                if response.status_code == 200:
                    jwks = response.json()
                    _clerk_jwks_cache = jwks
                    return jwks
                else:
                    logger.error(f"Failed to fetch JWKS: {response.status_code}")
                    return None
        except Exception as e:
            logger.error(f"Error fetching JWKS: {e}", exc_info=True)
            return None

    async def verify_clerk_token(self, token: str) -> dict[str, Any] | None:
        """
        Verify a Clerk JWT token and return user information.

        For development: If JWKS verification fails, falls back to decoding without verification.
        For production: Should strictly verify signatures.

        Args:
            token: The Clerk JWT token to verify

        Returns:
            Dict with user information if valid, None if invalid
        """
        try:
            # Remove 'Bearer ' prefix if present
            if token.startswith("Bearer "):
                token = token[7:]

            # Decode header to get key ID (kid)
            unverified_header = jwt.get_unverified_header(token)
            kid = unverified_header.get("kid")

            # Try to verify signature using Clerk's public keys
            jwks = await self._get_clerk_jwks()

            if jwks and kid:
                # Find the matching key
                key = None
                for jwk in jwks.get("keys", []):
                    if jwk.get("kid") == kid:
                        key = jwk
                        break

                if key:
                    try:
                        # Import cryptography for JWK to RSA key conversion
                        from jose import jwk

                        # Convert JWK to RSA key
                        rsa_key = jwk.construct(key)

                        # Verify token signature
                        payload = jwt.decode(
                            token,
                            rsa_key,
                            algorithms=["RS256"],  # Clerk uses RS256
                            options={
                                "verify_signature": True,
                                "verify_exp": True,
                                "verify_iat": True,
                            },
                        )
                        return payload
                    except JWTError as e:
                        logger.warning(f"JWT verification failed: {e}")
                        # Fall through to fallback for development
                    except Exception as e:
                        logger.error(f"Error converting JWK: {e}", exc_info=True)
                        # Fall through to fallback for development

            # Fallback: For development, decode without verification
            # TODO: Remove this fallback in production or make it configurable
            is_dev = os.getenv("ENVIRONMENT", "development").lower() == "development"
            if is_dev:
                logger.debug(
                    "Using development mode: decoding without signature verification"
                )
                try:
                    payload = jwt.decode(
                        token,
                        key="",  # Empty string when skipping verification
                        options={
                            "verify_signature": False,  # Skip signature verification in dev
                            "verify_exp": False,  # Skip expiration check in dev too
                        },
                    )
                    logger.debug(
                        f"Successfully decoded token. Payload keys: {list(payload.keys())}"
                    )
                    logger.debug(f"Payload contents: {payload}")
                    return payload
                except Exception as decode_error:
                    logger.error(
                        f"Decode error in dev mode: {decode_error}", exc_info=True
                    )
                    raise
            else:
                # Production: strict verification required
                logger.error(
                    "Production mode: signature verification required but failed"
                )
                return None

        except JWTError as e:
            logger.error(f"JWT Error: {e}")
            return None
        except Exception as e:
            logger.error(f"Token verification error: {e}", exc_info=True)
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
                    logger.error(
                        f"Clerk API error: {response.status_code} - {response.text}"
                    )
                    return None

        except Exception as e:
            logger.error(f"Error fetching user from Clerk: {e}", exc_info=True)
            return None

    def extract_user_data(self, clerk_payload: dict[str, Any]) -> dict[str, Any]:
        """
        Extract standardized user data from Clerk token payload

        Args:
            clerk_payload: The decoded Clerk JWT payload

        Returns:
            Standardized user data dictionary
        """
        first_name = (
            clerk_payload.get("given_name")
            or clerk_payload.get("first_name")
            or ""
        )
        last_name = (
            clerk_payload.get("family_name")
            or clerk_payload.get("last_name")
            or ""
        )

        if (not first_name or not last_name) and clerk_payload.get("name"):
            name_parts = clerk_payload.get("name", "").strip().split()
            if name_parts:
                first_name = first_name or name_parts[0]
                if len(name_parts) > 1:
                    last_name = last_name or " ".join(name_parts[1:])

        first_name = first_name.strip()
        last_name = last_name.strip()
        full_name = (
            clerk_payload.get("name")
            or f"{first_name} {last_name}".strip()
        )

        # Extract common fields from Clerk token
        return {
            "clerk_user_id": clerk_payload.get("sub"),  # Clerk user ID
            "email": clerk_payload.get("email"),
            "email_verified": clerk_payload.get("email_verified", False),
            "username": clerk_payload.get("username"),
            "first_name": first_name or None,
            "last_name": last_name or None,
            "full_name": full_name if full_name else None,
            "image_url": clerk_payload.get("picture"),
            "created_at": clerk_payload.get("iat"),  # Issued at time
        }


# Global Clerk auth instance
clerk_auth = ClerkAuth()
