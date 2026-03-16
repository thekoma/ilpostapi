"""Tests for profile page and token regeneration."""
import pytest
from httpx import AsyncClient

from tests.conftest import create_admin_via_setup


@pytest.mark.asyncio(loop_scope="session")
class TestProfile:
    async def test_profile_requires_auth(self, client: AsyncClient):
        await create_admin_via_setup(client)
        await client.get("/auth/logout", follow_redirects=False)
        resp = await client.get("/profile", follow_redirects=False)
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["location"]

    async def test_profile_renders(self, client: AsyncClient):
        await create_admin_via_setup(client)
        resp = await client.get("/profile")
        assert resp.status_code == 200
        assert "admin" in resp.text.lower()
        assert "Token RSS" in resp.text

    async def test_profile_shows_rss_token(self, client: AsyncClient):
        await create_admin_via_setup(client)
        resp = await client.get("/profile")
        assert resp.status_code == 200
        # Token should be visible in the page
        assert "/podcast/123/rss/" in resp.text  # example URL

    async def test_profile_shows_user_info(self, client: AsyncClient):
        await create_admin_via_setup(client)
        resp = await client.get("/profile")
        assert "admin@test.com" in resp.text
        assert "Admin" in resp.text  # capitalized role


@pytest.mark.asyncio(loop_scope="session")
class TestRegenerateToken:
    async def test_regenerate_token_requires_auth(self, client: AsyncClient):
        await create_admin_via_setup(client)
        await client.get("/auth/logout", follow_redirects=False)
        resp = await client.post("/profile/regenerate-token", follow_redirects=False)
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["location"]

    async def test_regenerate_token_changes_token(self, client: AsyncClient):
        await create_admin_via_setup(client)

        # Get current token from profile
        resp1 = await client.get("/profile")
        page1 = resp1.text

        # Regenerate
        resp = await client.post("/profile/regenerate-token", follow_redirects=False)
        assert resp.status_code == 302

        # Get new token from profile
        resp2 = await client.get("/profile")
        page2 = resp2.text

        # Extract tokens from the rss-token span
        import re
        token1 = re.search(r'id="rss-token">([^<]+)<', page1)
        token2 = re.search(r'id="rss-token">([^<]+)<', page2)
        assert token1 is not None
        assert token2 is not None
        assert token1.group(1) != token2.group(1)
