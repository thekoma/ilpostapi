"""Tests for database/user_operations.py - all CRUD and password operations."""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from database.user_operations import (
    create_user, get_user_count, get_user_by_id, get_user_by_username,
    get_user_by_email, get_user_by_oauth_sub, get_user_by_rss_token,
    get_all_users, update_user_password, regenerate_rss_token,
    delete_user, update_user_oauth_sub, verify_password, _hash_password,
)


class TestPasswordHashing:
    def test_hash_password_returns_string(self):
        h = _hash_password("testpassword")
        assert isinstance(h, str)
        assert h.startswith("$2b$")

    def test_hash_password_different_each_time(self):
        h1 = _hash_password("same")
        h2 = _hash_password("same")
        assert h1 != h2  # different salts

    def test_verify_password_correct(self):
        h = _hash_password("mypassword")
        assert verify_password("mypassword", h) is True

    def test_verify_password_wrong(self):
        h = _hash_password("mypassword")
        assert verify_password("wrongpassword", h) is False

    def test_verify_password_empty(self):
        h = _hash_password("something")
        assert verify_password("", h) is False


@pytest.mark.asyncio(loop_scope="session")
class TestCreateUser:
    async def test_create_user_with_password(self, db_session: AsyncSession):
        user = await create_user(db_session, "user1", "user1@test.com", "password123", "user")
        assert user.id is not None
        assert user.username == "user1"
        assert user.email == "user1@test.com"
        assert user.role == "user"
        assert user.password_hash is not None
        assert user.rss_token is not None
        assert len(user.rss_token) > 20
        assert user.oauth_sub is None

    async def test_create_user_without_password(self, db_session: AsyncSession):
        user = await create_user(db_session, "oauth_user", "oauth@test.com", role="user", oauth_sub="sub123")
        assert user.password_hash is None
        assert user.oauth_sub == "sub123"

    async def test_create_admin(self, db_session: AsyncSession):
        user = await create_user(db_session, "admin1", "admin1@test.com", "password123", "admin")
        assert user.role == "admin"
        assert user.is_admin is True

    async def test_create_user_unique_rss_tokens(self, db_session: AsyncSession):
        u1 = await create_user(db_session, "tok1", "tok1@test.com", "pass1234")
        u2 = await create_user(db_session, "tok2", "tok2@test.com", "pass1234")
        assert u1.rss_token != u2.rss_token


@pytest.mark.asyncio(loop_scope="session")
class TestGetUser:
    async def test_get_user_count_empty(self, db_session: AsyncSession):
        count = await get_user_count(db_session)
        assert count == 0

    async def test_get_user_count_with_users(self, db_session: AsyncSession):
        await create_user(db_session, "cnt1", "cnt1@test.com", "pass1234")
        await create_user(db_session, "cnt2", "cnt2@test.com", "pass1234")
        count = await get_user_count(db_session)
        assert count == 2

    async def test_get_user_by_id(self, db_session: AsyncSession):
        user = await create_user(db_session, "byid", "byid@test.com", "pass1234")
        found = await get_user_by_id(db_session, user.id)
        assert found is not None
        assert found.username == "byid"

    async def test_get_user_by_id_not_found(self, db_session: AsyncSession):
        found = await get_user_by_id(db_session, 99999)
        assert found is None

    async def test_get_user_by_username(self, db_session: AsyncSession):
        await create_user(db_session, "findme", "findme@test.com", "pass1234")
        found = await get_user_by_username(db_session, "findme")
        assert found is not None
        assert found.email == "findme@test.com"

    async def test_get_user_by_username_not_found(self, db_session: AsyncSession):
        found = await get_user_by_username(db_session, "nonexistent")
        assert found is None

    async def test_get_user_by_email(self, db_session: AsyncSession):
        await create_user(db_session, "emailuser", "email@test.com", "pass1234")
        found = await get_user_by_email(db_session, "email@test.com")
        assert found is not None
        assert found.username == "emailuser"

    async def test_get_user_by_email_not_found(self, db_session: AsyncSession):
        found = await get_user_by_email(db_session, "nope@nope.com")
        assert found is None

    async def test_get_user_by_oauth_sub(self, db_session: AsyncSession):
        await create_user(db_session, "oauthuser", "oauthfind@test.com", oauth_sub="sub-abc")
        found = await get_user_by_oauth_sub(db_session, "sub-abc")
        assert found is not None
        assert found.username == "oauthuser"

    async def test_get_user_by_oauth_sub_not_found(self, db_session: AsyncSession):
        found = await get_user_by_oauth_sub(db_session, "sub-nonexistent")
        assert found is None

    async def test_get_user_by_rss_token(self, db_session: AsyncSession):
        user = await create_user(db_session, "rssuser", "rss@test.com", "pass1234")
        found = await get_user_by_rss_token(db_session, user.rss_token)
        assert found is not None
        assert found.username == "rssuser"

    async def test_get_user_by_rss_token_not_found(self, db_session: AsyncSession):
        found = await get_user_by_rss_token(db_session, "invalid-token")
        assert found is None

    async def test_get_all_users(self, db_session: AsyncSession):
        await create_user(db_session, "all1", "all1@test.com", "pass1234")
        await create_user(db_session, "all2", "all2@test.com", "pass1234")
        users = await get_all_users(db_session)
        assert len(users) >= 2
        # Should be ordered by id
        ids = [u.id for u in users]
        assert ids == sorted(ids)


@pytest.mark.asyncio(loop_scope="session")
class TestUpdateUser:
    async def test_update_user_password(self, db_session: AsyncSession):
        user = await create_user(db_session, "pwchange", "pwchange@test.com", "oldpass123")
        old_hash = user.password_hash
        await update_user_password(db_session, user, "newpass456")
        assert user.password_hash != old_hash
        assert verify_password("newpass456", user.password_hash)
        assert not verify_password("oldpass123", user.password_hash)

    async def test_regenerate_rss_token(self, db_session: AsyncSession):
        user = await create_user(db_session, "regen", "regen@test.com", "pass1234")
        old_token = user.rss_token
        new_token = await regenerate_rss_token(db_session, user)
        assert new_token != old_token
        assert user.rss_token == new_token

    async def test_update_user_oauth_sub(self, db_session: AsyncSession):
        user = await create_user(db_session, "linkoauth", "linkoauth@test.com", "pass1234")
        assert user.oauth_sub is None
        await update_user_oauth_sub(db_session, user, "new-sub-id")
        assert user.oauth_sub == "new-sub-id"


@pytest.mark.asyncio(loop_scope="session")
class TestDeleteUser:
    async def test_delete_user(self, db_session: AsyncSession):
        user = await create_user(db_session, "delme", "delme@test.com", "pass1234")
        user_id = user.id
        result = await delete_user(db_session, user_id)
        assert result is True
        found = await get_user_by_id(db_session, user_id)
        assert found is None

    async def test_delete_user_not_found(self, db_session: AsyncSession):
        result = await delete_user(db_session, 99999)
        assert result is False


@pytest.mark.asyncio(loop_scope="session")
class TestUserModel:
    async def test_is_admin_property(self, db_session: AsyncSession):
        admin = await create_user(db_session, "isadmin", "isadmin@test.com", "pass1234", "admin")
        user = await create_user(db_session, "isuser", "isuser@test.com", "pass1234", "user")
        assert admin.is_admin is True
        assert user.is_admin is False
