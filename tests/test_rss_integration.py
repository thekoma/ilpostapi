"""Test di integrazione per il flusso RSS completo.

Questi test mockano solo le chiamate verso l'API esterna di Il Post
e lasciano girare il DB reale (SQLite) per verificare l'intero flusso:
API esterna → salvataggio DB → lettura DB → generazione RSS → ETag → 304.
"""
import feedparser
import pytest
from unittest.mock import patch
from httpx import AsyncClient

from tests.conftest import create_admin_via_setup


PODCAST_ID = 99

MOCK_API_EPISODES = {
    "head": {"data": {"total": 3, "pg": 1, "hits": 500}},
    "data": [
        {
            "id": 1001,
            "title": "Primo episodio",
            "description": "Descrizione breve",
            "content_html": "<p>Contenuto <strong>HTML</strong> del primo episodio.</p>",
            "summary": "Riassunto primo episodio",
            "episode_raw_url": "https://cdn.ilpost.it/ep1.mp3",
            "author": "Marco Rossi",
            "image": "https://cdn.ilpost.it/ep1.jpg",
            "share_url": "https://www.ilpost.it/episodes/ep1",
            "slug": "primo-episodio",
            "date": "2026-03-20T08:00:00+01:00",
            "milliseconds": 1800000,
            "special": 0,
            "parent": {
                "id": PODCAST_ID,
                "title": "Il Podcast Test",
                "description": "Un podcast di test per le integrazioni.",
                "author": "Marco Rossi",
                "image": "https://cdn.ilpost.it/podcast-test.jpg",
                "share_url": "https://www.ilpost.it/podcasts/test",
                "slug": "il-podcast-test",
            },
        },
        {
            "id": 1002,
            "title": "Secondo episodio",
            "description": "",
            "content_html": "<p>Secondo episodio con contenuto.</p>",
            "summary": "",
            "episode_raw_url": "https://cdn.ilpost.it/ep2.mp3",
            "author": "Marco Rossi",
            "image": "",
            "share_url": "",
            "slug": "secondo-episodio",
            "date": "2026-03-21T08:00:00+01:00",
            "milliseconds": 900000,
            "special": 0,
            "parent": {
                "id": PODCAST_ID,
                "title": "Il Podcast Test",
                "description": "Un podcast di test per le integrazioni.",
                "author": "Marco Rossi",
                "image": "https://cdn.ilpost.it/podcast-test.jpg",
                "share_url": "https://www.ilpost.it/podcasts/test",
                "slug": "il-podcast-test",
            },
        },
        {
            "id": 1003,
            "title": "Episodio bonus",
            "description": "Un episodio speciale",
            "content_html": "<p>Bonus!</p>",
            "summary": "Bonus",
            "episode_raw_url": "https://cdn.ilpost.it/ep3.mp3",
            "author": "",
            "image": "",
            "share_url": "",
            "slug": "episodio-bonus",
            "date": "2026-03-22T10:00:00+01:00",
            "milliseconds": 600000,
            "special": 1,
            "parent": {
                "id": PODCAST_ID,
                "title": "Il Podcast Test",
                "description": "Un podcast di test per le integrazioni.",
                "author": "Marco Rossi",
                "image": "https://cdn.ilpost.it/podcast-test.jpg",
                "share_url": "https://www.ilpost.it/podcasts/test",
                "slug": "il-podcast-test",
            },
        },
    ],
}

MOCK_BATCH_EPISODES = {
    "head": {"data": {"total": 3}},
    "data": [
        {"id": 1001, "content_html": "<p>Aggiornata 1.</p>", "description": "Agg"},
        {"id": 1002, "content_html": "<p>Aggiornata 2.</p>", "description": "Agg"},
        {"id": 1003, "content_html": "<p>Aggiornata 3.</p>", "description": "Agg"},
    ],
}


async def _setup_and_get_token(client: AsyncClient) -> str:
    """Crea admin e restituisce il token RSS."""
    await create_admin_via_setup(client)
    from database.database import AsyncSessionLocal
    from database.user_operations import get_user_by_username
    async with AsyncSessionLocal() as db:
        user = await get_user_by_username(db, "admin")
        return user.rss_token


async def _populate_db(client: AsyncClient, token: str):
    """Popola il DB con dati mock tramite una prima richiesta RSS."""
    with patch("routes.api.fetch_all_episodes", return_value=MOCK_API_EPISODES):
        resp = await client.get(f"/podcast/{PODCAST_ID}/rss/{token}")
        assert resp.status_code == 200
    return resp


@pytest.mark.asyncio(loop_scope="session")
class TestRssIntegrationFlow:
    """Testa il flusso completo: prima richiesta → DB → seconda richiesta."""

    async def test_first_request_saves_to_db(self, client: AsyncClient):
        """La prima richiesta deve chiamare l'API esterna e salvare podcast + episodi nel DB."""
        token = await _setup_and_get_token(client)

        with patch("routes.api.fetch_all_episodes", return_value=MOCK_API_EPISODES) as mock_fetch:
            resp = await client.get(f"/podcast/{PODCAST_ID}/rss/{token}")
            assert resp.status_code == 200
            assert "application/rss+xml" in resp.headers["content-type"]
            mock_fetch.assert_called_once()

        # Verifica che il podcast sia stato salvato nel DB
        from database.database import AsyncSessionLocal
        from database.operations import get_podcast_by_ilpost_id
        async with AsyncSessionLocal() as db:
            podcast = await get_podcast_by_ilpost_id(db, str(PODCAST_ID))
            assert podcast is not None
            assert podcast.title == "Il Podcast Test"
            assert podcast.author == "Marco Rossi"

    async def test_second_request_no_api_and_valid_feed(self, client: AsyncClient):
        """Dopo il primo fetch, le richieste successive non chiamano l'API e generano un feed valido."""
        token = await _setup_and_get_token(client)
        await _populate_db(client, token)

        # Seconda richiesta: il DB è aggiornato, nessuna chiamata API
        with patch("routes.api.fetch_all_episodes") as mock_fetch:
            resp = await client.get(f"/podcast/{PODCAST_ID}/rss/{token}")
            assert resp.status_code == 200
            mock_fetch.assert_not_called()

        # Il feed deve essere valido e completo
        feed = feedparser.parse(resp.text)
        assert feed.bozo == 0, f"Feed non valido: {feed.bozo_exception}"
        assert feed.feed.title == "Il Podcast Test"
        assert feed.feed.language == "it"
        assert len(feed.entries) == 3

    async def test_fetch_podcasts_never_called(self, client: AsyncClient):
        """fetch_podcasts() non deve mai essere chiamata nel percorso RSS."""
        token = await _setup_and_get_token(client)
        await _populate_db(client, token)

        with patch("routes.api.fetch_podcasts") as mock_fp:
            resp = await client.get(f"/podcast/{PODCAST_ID}/rss/{token}")
            assert resp.status_code == 200
            mock_fp.assert_not_called()


@pytest.mark.asyncio(loop_scope="session")
class TestEtagIntegration:
    """Testa il flusso ETag end-to-end con DB reale."""

    async def test_etag_full_cycle(self, client: AsyncClient):
        """200 con ETag → 304 con If-None-Match → 200 con ETag diverso."""
        token = await _setup_and_get_token(client)
        resp1 = await _populate_db(client, token)

        etag = resp1.headers["etag"]
        assert etag.startswith('"') and etag.endswith('"')
        assert "cache-control" in resp1.headers
        assert "max-age=300" in resp1.headers["cache-control"]

        # If-None-Match con stesso ETag → 304
        resp2 = await client.get(
            f"/podcast/{PODCAST_ID}/rss/{token}",
            headers={"If-None-Match": etag},
        )
        assert resp2.status_code == 304
        assert resp2.headers["etag"] == etag
        assert len(resp2.content) == 0

        # If-None-Match con ETag diverso → 200
        resp3 = await client.get(
            f"/podcast/{PODCAST_ID}/rss/{token}",
            headers={"If-None-Match": '"vecchio-etag"'},
        )
        assert resp3.status_code == 200
        assert resp3.headers["etag"] == etag

    async def test_last_modified_and_if_modified_since(self, client: AsyncClient):
        """Last-Modified presente e If-Modified-Since → 304."""
        token = await _setup_and_get_token(client)
        resp1 = await _populate_db(client, token)

        assert "last-modified" in resp1.headers
        last_modified = resp1.headers["last-modified"]
        assert "2026" in last_modified

        # If-Modified-Since con stessa data → 304
        resp2 = await client.get(
            f"/podcast/{PODCAST_ID}/rss/{token}",
            headers={"If-Modified-Since": last_modified},
        )
        assert resp2.status_code == 304


@pytest.mark.asyncio(loop_scope="session")
class TestBatchDescriptionUpdate:
    """Testa l'aggiornamento descrizioni in batch."""

    async def test_batch_update_and_skip_when_verified(self, client: AsyncClient):
        """Descrizioni non verificate → aggiornamento batch. Poi, nessuna chiamata batch."""
        token = await _setup_and_get_token(client)
        await _populate_db(client, token)

        # Segna episodi come non verificati
        from database.database import AsyncSessionLocal
        from database.models import Episode
        from sqlalchemy import update, select

        async with AsyncSessionLocal() as db:
            await db.execute(update(Episode).values(description_verified=False))
            await db.commit()

        # Richiesta con episodi non verificati → deve chiamare batch
        with patch("routes.api.fetch_episodes_batch", return_value=MOCK_BATCH_EPISODES) as mock_batch:
            resp = await client.get(f"/podcast/{PODCAST_ID}/rss/{token}")
            assert resp.status_code == 200
            mock_batch.assert_called_once()

        # Verifica che le descrizioni siano state aggiornate nel DB
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Episode))
            episodes = result.scalars().all()
            our_episodes = [ep for ep in episodes if int(ep.ilpost_id) in (1001, 1002, 1003)]
            for ep in our_episodes:
                assert ep.description_verified, f"Episodio {ep.ilpost_id} non verificato"

        # Ora sono tutti verificati → nessuna chiamata batch
        with patch("routes.api.fetch_episodes_batch") as mock_batch:
            resp = await client.get(f"/podcast/{PODCAST_ID}/rss/{token}")
            assert resp.status_code == 200
            mock_batch.assert_not_called()
