from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional

from app.core.clerk_auth import clerk_auth
from app.core.repository import repo
from app.core.schemas import User, ClerkUserSync

security = HTTPBearer()


async def get_current_user_from_clerk(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> User:
    """
    Dependency to get current user from Clerk JWT token.
    
    This function:
    1. Verifies the Clerk JWT token
    2. Syncs user data to MongoDB if needed
    3. Returns the user from our database
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # Verify Clerk token
        clerk_payload = await clerk_auth.verify_clerk_token(credentials.credentials)
        if not clerk_payload:
            raise credentials_exception
        
        # Extract user data from Clerk token
        user_data = clerk_auth.extract_user_data(clerk_payload)
        
        if not user_data.get("clerk_user_id") or not user_data.get("email"):
            raise credentials_exception
        
        # Check if user exists in our database
        existing_user = await repo.get_user_by_clerk_id(user_data["clerk_user_id"])
        
        if existing_user:
            # User exists, return it
            return existing_user
        else:
            # User doesn't exist, sync from Clerk
            clerk_user_data = ClerkUserSync(**user_data)
            synced_user = await repo.sync_clerk_user(clerk_user_data)
            return synced_user
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"Authentication error: {e}")
        raise credentials_exception


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))
) -> Optional[User]:
    """
    Optional dependency to get current user from Clerk JWT token.
    Returns None if no token is provided or invalid.
    """
    if not credentials:
        return None
    
    try:
        return await get_current_user_from_clerk(credentials)
    except HTTPException:
        return None


async def get_current_active_user(
    current_user: User = Depends(get_current_user_from_clerk)
) -> User:
    """
    Dependency to get current active user.
    Raises HTTP 400 if user is inactive.
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    return current_user


# Alias for backwards compatibility
get_current_user = get_current_user_from_clerk
