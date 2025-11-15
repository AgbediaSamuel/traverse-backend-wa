"""
CSRF Protection Middleware

Validates Origin header for state-changing requests to prevent CSRF attacks.
"""

import os
from typing import Callable

from fastapi import HTTPException, Request, status
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware

# Allowed origins for development
ALLOWED_ORIGINS = [
    "http://localhost:3456",  # Next.js frontend
    "http://localhost:5174",  # Vite itinerary template
    "http://127.0.0.1:3456",
    "http://127.0.0.1:5174",
]

# Add production origins from environment if set
# For ngrok: set ALLOWED_ORIGINS=https://xxx.ngrok-free.dev
PROD_ORIGINS = os.getenv("ALLOWED_ORIGINS", "").split(",")
ALLOWED_ORIGINS.extend([origin.strip() for origin in PROD_ORIGINS if origin.strip()])

# State-changing HTTP methods that need CSRF protection
STATE_CHANGING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class CSRFProtectionMiddleware(BaseHTTPMiddleware):
    """
    Middleware to validate Origin header for state-changing requests.

    This prevents CSRF attacks by ensuring requests come from allowed origins.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip CSRF check for webhook routes (Clerk sends webhooks from different origin)
        if request.url.path.startswith("/webhooks/"):
            return await call_next(request)
<<<<<<< HEAD

=======
        
>>>>>>> master
        # Only check state-changing methods
        if request.method not in STATE_CHANGING_METHODS:
            return await call_next(request)

        # Get Origin header
        origin = request.headers.get("Origin")
        referer = request.headers.get("Referer")

        # Allow requests without Origin (e.g., same-origin, Postman, curl)
        # But validate Referer if Origin is missing
        if not origin:
            # For same-origin requests, Origin might be missing
            # Check Referer as fallback
            if referer:
                # Extract origin from referer
                try:
                    from urllib.parse import urlparse

                    parsed = urlparse(referer)
                    origin = f"{parsed.scheme}://{parsed.netloc}"
                except Exception:
                    pass

        # If we have an origin, validate it
        if origin:
            # Remove trailing slash for comparison
            origin = origin.rstrip("/")

            # Check against allowed origins
            if origin not in ALLOWED_ORIGINS:
                # Log for debugging (but don't expose in production)
                print(
                    f"[CSRF] Rejected request from origin: {origin}"
                    f" (allowed: {ALLOWED_ORIGINS})"
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Origin not allowed",
                )

        # Continue with request
        return await call_next(request)
