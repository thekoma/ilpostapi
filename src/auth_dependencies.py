from fastapi import Depends, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from database.user_operations import get_user_by_id, get_user_count


class AuthRedirect(Exception):
    """Raised when user needs to be redirected for auth."""
    def __init__(self, url: str):
        self.url = url


async def get_current_user_optional(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Returns the current user from session, or None if not logged in."""
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return await get_user_by_id(db, user_id)


async def require_auth(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Dependency that requires authentication. Raises AuthRedirect if not logged in."""
    user_id = request.session.get("user_id")
    if not user_id:
        user_count = await get_user_count(db)
        if user_count == 0:
            raise AuthRedirect("/auth/setup")
        raise AuthRedirect("/auth/login")

    user = await get_user_by_id(db, user_id)
    if not user:
        request.session.clear()
        raise AuthRedirect("/auth/login")
    return user


async def require_admin(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Dependency that requires admin role."""
    user = await require_auth(request, db)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Accesso negato")
    return user
