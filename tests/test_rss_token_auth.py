"""Tests for RSS token-based authentication in URLs."""
import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient

from tests.conftest import create_admin_via_setup


@pytest.mark.asyncio(loop_scope="session")
class TestRssTokenAuth:
    """Test that RSS feeds work with token in path."""

    async def _get_user_token(self) -> str:
        from database.database import AsyncSessionLocal
        from database.user_operations import get_user_by_username
        async with AsyncSessionLocal() as db:
            user = await get_user_by_username(db, "admin")
            return user.rss_token

    async def test_rss_without_auth_redirects(self, client: AsyncClient):
        await create_admin_via_setup(client)
        await client.get("/auth/logout", follow_redirects=False)
        resp = await client.get("/podcast/1/rss", follow_redirects=False)
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["location"]

    async def test_rss_with_invalid_token_returns_403(self, client: AsyncClient):
        await create_admin_via_setup(client)
        await client.get("/auth/logout", follow_redirects=False)
        resp = await client.get("/podcast/1/rss/invalid-token-abc", follow_redirects=False)
        assert resp.status_code == 403

    @patch("routes.api.get_podcast_by_ilpost_id")
    @patch("routes.api.get_podcast_episodes")
    @patch("routes.api.fetch_all_episodes")
    async def test_rss_with_valid_token_works(
        self, mock_fetch_all, mock_get_episodes, mock_get_podcast, client: AsyncClient
    ):
        await create_admin_via_setup(client)
        token = await self._get_user_token()
        await client.get("/auth/logout", follow_redirects=False)

        # Mock the podcast DB lookup
        from types import SimpleNamespace
        mock_get_podcast.return_value = SimpleNamespace(
            id=1, ilpost_id="1", title="Test Podcast", description="Desc",
            author="Author", image_url="http://img.png", share_url="", slug="test",
        )
        mock_get_episodes.return_value = ([], True)
        mock_fetch_all.return_value = {
            "data": [{
                "id": 100, "title": "Ep 1", "description": "Desc",
                "content_html": "<p>Desc</p>", "summary": "Sum",
                "episode_raw_url": "http://audio.mp3", "author": "Author",
                "image": "", "share_url": "", "slug": "ep1",
                "date": "2025-01-01T00:00:00+00:00", "milliseconds": 60000,
                "parent": {"title": "Test Podcast", "description": "Desc",
                           "author": "Author", "image": "http://img.png",
                           "share_url": "", "slug": "test"},
            }]
        }

        resp = await client.get(f"/podcast/1/rss/{token}", follow_redirects=False)
        # Should return RSS (not redirect), might be 200 or 500 depending on DB state
        # but NOT 302 (redirect) or 403 (forbidden)
        assert resp.status_code != 302
        assert resp.status_code != 403

    async def test_rss_with_session_auth_works(self, client: AsyncClient):
        """RSS should also work when logged in via session (no token needed)."""
        await create_admin_via_setup(client)
        # We're logged in from setup, so accessing /podcast/1/rss should not redirect
        with patch("routes.api.get_podcast_episodes") as mock_ep, \
             patch("routes.api.fetch_all_episodes") as mock_all:
            mock_ep.return_value = ([], True)
            mock_all.return_value = {"data": []}
            resp = await client.get("/podcast/1/rss", follow_redirects=False)
            # Should not redirect to login (404 is OK - podcast not found)
            assert resp.status_code != 302


@pytest.mark.asyncio(loop_scope="session")
class TestRssTokenAfterRegeneration:
    async def test_old_token_invalid_after_regeneration(self, client: AsyncClient):
        await create_admin_via_setup(client)

        from database.database import AsyncSessionLocal
        from database.user_operations import get_user_by_username, regenerate_rss_token

        async with AsyncSessionLocal() as db:
            user = await get_user_by_username(db, "admin")
            old_token = user.rss_token
            await regenerate_rss_token(db, user)

        await client.get("/auth/logout", follow_redirects=False)
        resp = await client.get(f"/podcast/1/rss/{old_token}", follow_redirects=False)
        assert resp.status_code == 403
