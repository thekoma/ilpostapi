"""OIDC callback: account matching and username collisions."""
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from database.database import AsyncSessionLocal
from database.models import User
from tests.conftest import create_admin_via_setup


def _mock_provider(sub: str, email: str, username: str, groups=None):
    """Patch routes.auth so the callback sees a fixed OIDC identity."""
    userinfo = {
        "sub": sub,
        "email": email,
        "preferred_username": username,
        "groups": groups or [],
    }
    provider = AsyncMock()
    provider.authorize_access_token.return_value = {"userinfo": userinfo}
    provider.userinfo.return_value = userinfo
    return [
        patch("routes.auth.OIDC_ENABLED", True),
        patch("routes.auth.oauth.authentik", provider, create=True),
    ]


async def _callback(client: AsyncClient, **identity):
    patches = _mock_provider(**identity)
    for p in patches:
        p.start()
    try:
        return await client.get("/auth/callback?code=x&state=y", follow_redirects=False)
    finally:
        for p in reversed(patches):
            p.stop()


async def _users():
    async with AsyncSessionLocal() as s:
        return list((await s.execute(select(User).order_by(User.id))).scalars())


@pytest.mark.asyncio(loop_scope="session")
class TestOidcCallback:
    async def test_new_identity_creates_user(self, client: AsyncClient):
        await create_admin_via_setup(client)  # local admin "admin"
        resp = await _callback(client, sub="sub-1", email="new@example.com", username="newbie")
        assert resp.status_code == 302 and resp.headers["location"] == "/"
        users = await _users()
        assert [u.username for u in users] == ["admin", "newbie"]
        assert users[1].oauth_sub == "sub-1"

    async def test_same_email_links_existing_local_user(self, client: AsyncClient):
        await create_admin_via_setup(client)
        local = (await _users())[0]
        resp = await _callback(client, sub="sub-2", email=local.email, username="whatever")
        assert resp.status_code == 302
        users = await _users()
        assert len(users) == 1 and users[0].oauth_sub == "sub-2"

    async def test_username_taken_with_other_email_is_refused_not_500(self, client: AsyncClient):
        await create_admin_via_setup(client)
        local = (await _users())[0]
        resp = await _callback(
            client, sub="sub-3", email="someone-else@example.com", username=local.username
        )
        assert resp.status_code == 409
        assert "Esiste già un account locale" in resp.text
        users = await _users()
        assert len(users) == 1 and users[0].oauth_sub is None  # nothing linked

    async def test_known_sub_logs_in_even_if_email_changed(self, client: AsyncClient):
        await create_admin_via_setup(client)
        await _callback(client, sub="sub-4", email="a@example.com", username="alice")
        resp = await _callback(client, sub="sub-4", email="changed@example.com", username="alice")
        assert resp.status_code == 302
        assert len(await _users()) == 2
