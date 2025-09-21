import pytest

from app.api.routers.users import get_user, list_users


@pytest.mark.asyncio
async def test_list_users_unit():
    users = await list_users()
    assert isinstance(users, list)
    assert len(users) >= 2


@pytest.mark.asyncio
async def test_get_user_unit_found():
    user = await get_user(1)
    assert user.id == 1


@pytest.mark.asyncio
async def test_get_user_unit_not_found():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await get_user(9999)
    assert exc.value.status_code == 404

