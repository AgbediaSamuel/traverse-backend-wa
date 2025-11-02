from app.core.repository import repo
from app.core.schemas import (
    ClerkUserSync,
    OnboardingUpdate,
    User,
    UserPreferences,
    UserPreferencesCreate,
)
from fastapi import APIRouter, HTTPException, status

# Create the router
router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/users", response_model=User)
async def create_or_update_user(user_data: ClerkUserSync):
    """
    Create or update user from Clerk data.

    Call this endpoint from your NextJS frontend after Clerk authentication
    to store/update the user in your MongoDB database.
    """
    try:
        user = await repo.sync_clerk_user(user_data)
        return user
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create/update user: {e!s}",
        )


@router.get("/users/{clerk_user_id}", response_model=User)
async def get_user_by_clerk_id(clerk_user_id: str):
    """
    Get user data by Clerk user ID.

    Use this to get user info from your database using the Clerk user ID.
    """
    user = await repo.get_user_by_clerk_id(clerk_user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return user


@router.get("/users/email/{email}", response_model=User)
async def get_user_by_email(email: str):
    """
    Get user data by email.
    """
    user = await repo.get_user_by_email(email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return user


@router.delete("/users/{clerk_user_id}")
async def delete_user(clerk_user_id: str):
    """
    Delete user from database (optional - for cleanup).
    """
    try:
        result = repo.users_collection.delete_one({"clerk_user_id": clerk_user_id})
        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )
        return {"message": "User deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete user: {e!s}",
        )


@router.patch("/users/{clerk_user_id}/onboarding", response_model=User)
async def update_user_onboarding(clerk_user_id: str, onboarding_data: OnboardingUpdate):
    """
    Update user onboarding status.

    Use this to mark onboarding as completed or skipped.
    """
    try:
        user = await repo.update_user_onboarding(
            clerk_user_id=clerk_user_id,
            onboarding_completed=onboarding_data.onboarding_completed,
            onboarding_skipped=onboarding_data.onboarding_skipped,
        )
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )
        return user
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update onboarding status: {e!s}",
        )


@router.post("/users/{clerk_user_id}/preferences", response_model=UserPreferences)
async def save_user_preferences(clerk_user_id: str, preferences: UserPreferencesCreate):
    """
    Save user travel preferences.

    Use this to store user preferences from the onboarding form.
    """
    try:
        # Verify user exists
        user = await repo.get_user_by_clerk_id(clerk_user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )

        # Save preferences
        saved_preferences = await repo.save_user_preferences(clerk_user_id, preferences)
        return saved_preferences
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save preferences: {e!s}",
        )


@router.get("/users/{clerk_user_id}/preferences", response_model=UserPreferences)
async def get_user_preferences(clerk_user_id: str):
    """
    Get user travel preferences by Clerk user ID.
    """
    try:
        preferences = await repo.get_user_preferences(clerk_user_id)
        if not preferences:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User preferences not found",
            )
        return preferences
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get preferences: {e!s}",
        )


@router.get("/test")
async def test_auth_endpoint():
    """Test endpoint to verify the auth router is working"""
    return {
        "message": "Simple Auth API is working!",
        "endpoints": {
            "POST /auth/users": "Create/update user from Clerk data",
            "GET /auth/users/{clerk_user_id}": "Get user by Clerk ID",
            "GET /auth/users/email/{email}": "Get user by email",
            "PATCH /auth/users/{clerk_user_id}/onboarding": "Update onboarding status",
            "POST /auth/users/{clerk_user_id}/preferences": "Save user preferences",
            "GET /auth/users/{clerk_user_id}/preferences": "Get user preferences",
            "DELETE /auth/users/{clerk_user_id}": "Delete user",
        },
        "usage": "Call POST /auth/users from your NextJS frontend after Clerk auth",
    }
