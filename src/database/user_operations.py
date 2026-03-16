import secrets
from typing import Optional

import bcrypt as _bcrypt
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from .models import User


def _hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()


def verify_password(plain_password: str, password_hash: str) -> bool:
    return _bcrypt.checkpw(plain_password.encode(), password_hash.encode())


async def get_user_count(db: AsyncSession) -> int:
    result = await db.execute(select(func.count(User.id)))
    return result.scalar()


async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_user_by_username(db: AsyncSession, username: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_oauth_sub(db: AsyncSession, oauth_sub: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.oauth_sub == oauth_sub))
    return result.scalar_one_or_none()


async def get_user_by_rss_token(db: AsyncSession, token: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.rss_token == token))
    return result.scalar_one_or_none()


async def get_all_users(db: AsyncSession) -> list[User]:
    result = await db.execute(select(User).order_by(User.id))
    return list(result.scalars().all())


async def create_user(
    db: AsyncSession,
    username: str,
    email: str,
    password: Optional[str] = None,
    role: str = "user",
    oauth_sub: Optional[str] = None,
) -> User:
    user = User(
        username=username,
        email=email,
        password_hash=_hash_password(password) if password else None,
        role=role,
        rss_token=secrets.token_urlsafe(32),
        oauth_sub=oauth_sub,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def update_user_password(db: AsyncSession, user: User, new_password: str) -> None:
    user.password_hash = _hash_password(new_password)
    await db.commit()


async def regenerate_rss_token(db: AsyncSession, user: User) -> str:
    user.rss_token = secrets.token_urlsafe(32)
    await db.commit()
    await db.refresh(user)
    return user.rss_token


async def delete_user(db: AsyncSession, user_id: int) -> bool:
    user = await get_user_by_id(db, user_id)
    if not user:
        return False
    await db.delete(user)
    await db.commit()
    return True


async def update_user_role(db: AsyncSession, user: User, role: str) -> None:
    if role not in ("admin", "user"):
        raise ValueError("Ruolo non valido")
    user.role = role
    await db.commit()


async def update_user_oauth_sub(db: AsyncSession, user: User, oauth_sub: str) -> None:
    user.oauth_sub = oauth_sub
    await db.commit()
