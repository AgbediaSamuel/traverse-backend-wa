from typing import Optional

from app.core.auth import verify_token
from app.core.repository import repo
from app.core.schemas import User
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# HTTP Bearer token security scheme
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User:
    """
    Dependency to get the current authenticated user from JWT token.

    This function:
    1. Extracts the Bearer token from the Authorization header
    2. Verifies the JWT token
    3. Retrieves the user from the database
    4. Returns the user object

    Args:
        credentials: The HTTP authorization credentials containing the Bearer token

    Returns:
        User: The authenticated user object

    Raises:
        HTTPException: 401 Unauthorized if token is invalid or user not found
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # Verify the JWT token and extract the email
        email = verify_token(credentials.credentials)
        if email is None:
            raise credentials_exception
    except Exception:
        raise credentials_exception

    # Get user from database
    user = await repo.get_user_by_email(email)
    if user is None:
        raise credentials_exception

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Dependency to get the current authenticated and active user.

    Args:
        current_user: The current user from get_current_user dependency

    Returns:
        User: The authenticated and active user object

    Raises:
        HTTPException: 400 Bad Request if user is inactive
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user"
        )
    return current_user


def get_optional_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[User]:
    """
    Dependency to optionally get the current user (for routes that work with or without auth).

    This is useful for endpoints that provide different functionality for
    authenticated vs anonymous users.

    Args:
        credentials: Optional HTTP authorization credentials

    Returns:
        Optional[User]: The user object if authenticated, None if not
    """
    if credentials is None:
        return None

    try:
        email = verify_token(credentials.credentials)
        if email is None:
            return None

        # Note: This should be async in a real app, but we'll keep it simple
        # In practice, you'd want to make this async and await the repo call
        user = repo.get_user_by_email_sync(email)  # We'll add this method
        return user
    except Exception:
        return None


class RequireScopes:
    """
    Dependency class to require specific user scopes/roles for route access.

    Usage:
        @router.get("/admin-only")
        async def admin_route(user: User = Depends(RequireScopes(["admin"]))):
            ...
    """

    def __init__(self, required_scopes: list[str]):
        self.required_scopes = required_scopes

    async def __call__(
        self, current_user: User = Depends(get_current_active_user)
    ) -> User:
        """
        Check if the current user has the required scopes.

        Args:
            current_user: The current authenticated user

        Returns:
            User: The user if they have required scopes

        Raises:
            HTTPException: 403 Forbidden if user lacks required scopes
        """
        # Note: This assumes you'll add a 'scopes' field to your User model
        user_scopes = getattr(current_user, "scopes", [])

        if not any(scope in user_scopes for scope in self.required_scopes):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions"
            )

        return current_user


# Convenience dependencies for common use cases
require_admin = RequireScopes(["admin"])
require_user = RequireScopes(["user", "admin"])  # Either user or admin
