"""Tests for ETag / Last-Modified conditional GET on RSS feeds."""
import pytest
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient

from tests.conftest import create_admin_via_setup


# Dati mock condivisi
MOCK_DB_PODCAST = SimpleNamespace(
    id=1,
    ilpost_id="1",
    title="Test Podcast",
    description="Desc",
    author="Author",
    image_url="http://img.png",
    share_url="",
    slug="test",
)

MOCK_EPISODES_DATA = {
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


def _rss_mocks():
    """Restituisce i decoratori patch comuni per i test RSS."""
    return [
        patch("routes.api.get_podcast_by_ilpost_id", return_value=MOCK_DB_PODCAST),
        patch("routes.api.get_podcast_episodes", return_value=([], True)),
        patch("routes.api.fetch_all_episodes", return_value=MOCK_EPISODES_DATA),
    ]


@pytest.mark.asyncio(loop_scope="session")
class TestConditionalGetRss:
    """Test ETag e Last-Modified per i feed RSS."""

    async def _get_user_token(self) -> str:
        from database.database import AsyncSessionLocal
        from database.user_operations import get_user_by_username
        async with AsyncSessionLocal() as db:
            user = await get_user_by_username(db, "admin")
            return user.rss_token

    async def test_rss_response_contains_etag(self, client: AsyncClient):
        """La risposta RSS deve contenere l'header ETag."""
        await create_admin_via_setup(client)
        token = await self._get_user_token()

        for m in _rss_mocks():
            m.start()
        try:
            resp = await client.get(f"/podcast/1/rss/{token}")
            assert resp.status_code == 200
            assert "etag" in resp.headers
            assert resp.headers["etag"].startswith('"')
            assert resp.headers["etag"].endswith('"')
        finally:
            patch.stopall()

    async def test_rss_response_contains_cache_control(self, client: AsyncClient):
        """La risposta RSS deve contenere Cache-Control."""
        await create_admin_via_setup(client)
        token = await self._get_user_token()

        for m in _rss_mocks():
            m.start()
        try:
            resp = await client.get(f"/podcast/1/rss/{token}")
            assert resp.status_code == 200
            assert "cache-control" in resp.headers
            assert "max-age=300" in resp.headers["cache-control"]
        finally:
            patch.stopall()

    async def test_rss_304_with_matching_etag(self, client: AsyncClient):
        """Se If-None-Match corrisponde all'ETag, deve restituire 304."""
        await create_admin_via_setup(client)
        token = await self._get_user_token()

        for m in _rss_mocks():
            m.start()
        try:
            # Prima richiesta: ottieni l'ETag
            resp1 = await client.get(f"/podcast/1/rss/{token}")
            assert resp1.status_code == 200
            etag = resp1.headers["etag"]

            # Seconda richiesta con If-None-Match
            resp2 = await client.get(
                f"/podcast/1/rss/{token}",
                headers={"If-None-Match": etag},
            )
            assert resp2.status_code == 304
            assert resp2.headers["etag"] == etag
            assert resp2.content == b""  # Nessun body nella 304
        finally:
            patch.stopall()

    async def test_rss_200_with_different_etag(self, client: AsyncClient):
        """Se If-None-Match non corrisponde, deve restituire 200."""
        await create_admin_via_setup(client)
        token = await self._get_user_token()

        for m in _rss_mocks():
            m.start()
        try:
            resp = await client.get(
                f"/podcast/1/rss/{token}",
                headers={"If-None-Match": '"stale-etag"'},
            )
            assert resp.status_code == 200
            assert "etag" in resp.headers
        finally:
            patch.stopall()
