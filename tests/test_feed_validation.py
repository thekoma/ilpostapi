"""Test di validazione RSS/RDF: genera feed con dati mock realistici e valida la struttura."""
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_tz
from types import SimpleNamespace

import feedparser
import pytest
from unittest.mock import patch
from httpx import AsyncClient

from tests.conftest import create_admin_via_setup


# Dati mock realistici
MOCK_PODCAST_INFO = {
    "id": 42,
    "title": "Morning",
    "description": "La rassegna stampa del Post, con Luca Misculin.",
    "author": "Luca Misculin",
    "image": "https://example.com/morning.jpg",
    "share_url": "https://www.ilpost.it/podcasts/morning",
    "slug": "morning",
}


def _make_episode(**overrides):
    """Crea un oggetto che simula un Episode del DB."""
    defaults = {
        "id": 1,
        "ilpost_id": "100",
        "podcast_id": 42,
        "title": "Episodio di test",
        "description": "Descrizione dell'episodio",
        "summary": "Riassunto",
        "description_verified": True,
        "audio_url": "https://cdn.example.com/ep.mp3",
        "author": "Luca Misculin",
        "image_url": "https://example.com/ep.jpg",
        "share_url": "https://www.ilpost.it/episodes/ep",
        "slug": "ep",
        "episode_type": "full",
        "publication_date": datetime(2026, 3, 14, 8, 0, 22, tzinfo=timezone(timedelta(hours=1))),
        "duration": 1347,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# Episodi con casistiche diverse
MOCK_DB_EPISODES = [
    _make_episode(
        id=1, ilpost_id="100",
        title="Episodio con tutti i campi",
        description="<p>Contenuto <strong>HTML</strong> completo.</p>",
        summary="Un riassunto dell'episodio",
        audio_url="https://cdn.example.com/ep1.mp3",
        author="Nicola Ghittoni",
        image_url="https://example.com/ep1.jpg",
        share_url="https://www.ilpost.it/episodes/ep1",
        publication_date=datetime(2026, 3, 14, 8, 0, 22, tzinfo=timezone(timedelta(hours=1))),
        duration=1347,
    ),
    _make_episode(
        id=2, ilpost_id="101",
        title="Episodio senza timezone nella data",
        description="Solo descrizione, niente content_html",
        summary="",
        audio_url="https://cdn.example.com/ep2.mp3",
        author="",
        image_url="",
        share_url="",
        # Data senza timezone (viene dal DB con timezone ma testiamo il generatore)
        publication_date=datetime(2026, 3, 13, 7, 30, 0, tzinfo=timezone(timedelta(hours=1))),
        duration=900,
    ),
    _make_episode(
        id=3, ilpost_id="102",
        title='Episodio con caratteri speciali: <Perche\'> & "virgolette"',
        description='<p data-slate-node="element">HTML con <a data-slate-inline="true" data-encore-id="link" href="#">link</a> e <em data-slate-leaf="true">enfasi</em></p>',
        summary="Riassunto con 'apici' e \"virgolette\"",
        audio_url="https://cdn.example.com/ep3.mp3",
        author="Luca Misculin",
        image_url="https://example.com/ep3.jpg",
        share_url="https://www.ilpost.it/episodes/ep3",
        publication_date=datetime(2026, 3, 12, 9, 0, 0, tzinfo=timezone(timedelta(hours=2))),
        duration=7500,
    ),
    _make_episode(
        id=4, ilpost_id="103",
        title="Episodio minimale",
        description="",
        summary="",
        audio_url="https://cdn.example.com/ep4.mp3",
        author="",
        image_url="",
        share_url="",
        publication_date=None,
        duration=None,
    ),
    _make_episode(
        id=5, ilpost_id="104",
        title="Episodio con URL ellipsis e style tag",
        description='<style>.foo{color:red}</style><p>Contenuto dopo style</p>',
        summary="",
        audio_url="https://www.example.com/podcast/tienimi-bordone-se-i-cattivi-sono-ricchi\u2026.mp3",
        author="Matteo Bordone",
        image_url="",
        share_url="",
        publication_date=datetime(2026, 3, 11, 10, 0, 0, tzinfo=timezone(timedelta(hours=1))),
        duration=655,
    ),
]


def _setup_mocks(mock_get_episodes, mock_fetch_podcasts):
    """Configura i mock per evitare il percorso di salvataggio nel DB."""
    mock_fetch_podcasts.return_value = {"data": [MOCK_PODCAST_INFO]}
    # Ritorna episodi con needs_update=False per evitare il save path
    mock_get_episodes.return_value = (MOCK_DB_EPISODES, False)


@pytest.mark.asyncio(loop_scope="session")
class TestRSSFeedValidation:
    """Valida la struttura del feed RSS generato."""

    @patch("routes.api.fetch_podcasts")
    @patch("routes.api.get_podcast_episodes")
    async def test_rss_is_valid_xml(
        self, mock_get_episodes, mock_fetch_podcasts, client: AsyncClient
    ):
        """Il feed deve essere XML ben formato."""
        await create_admin_via_setup(client)
        _setup_mocks(mock_get_episodes, mock_fetch_podcasts)

        resp = await client.get("/podcast/42/rss", follow_redirects=False)
        assert resp.status_code == 200
        assert "application/rss+xml" in resp.headers["content-type"]
        ET.fromstring(resp.text)

    @patch("routes.api.fetch_podcasts")
    @patch("routes.api.get_podcast_episodes")
    async def test_rss_feedparser_no_bozo(
        self, mock_get_episodes, mock_fetch_podcasts, client: AsyncClient
    ):
        """feedparser non deve segnalare errori (bozo=0)."""
        await create_admin_via_setup(client)
        _setup_mocks(mock_get_episodes, mock_fetch_podcasts)

        resp = await client.get("/podcast/42/rss", follow_redirects=False)
        feed = feedparser.parse(resp.text)
        assert feed.bozo == 0, f"feedparser ha trovato errori: {feed.bozo_exception}"

    @patch("routes.api.fetch_podcasts")
    @patch("routes.api.get_podcast_episodes")
    async def test_rss_channel_required_elements(
        self, mock_get_episodes, mock_fetch_podcasts, client: AsyncClient
    ):
        """Il channel deve avere title, link, description (richiesti da RSS 2.0)."""
        await create_admin_via_setup(client)
        _setup_mocks(mock_get_episodes, mock_fetch_podcasts)

        resp = await client.get("/podcast/42/rss", follow_redirects=False)
        feed = feedparser.parse(resp.text)

        assert feed.feed.get("title") == "Morning"
        assert feed.feed.get("link")
        assert feed.feed.get("description")
        assert feed.feed.get("language") == "it"

    @patch("routes.api.fetch_podcasts")
    @patch("routes.api.get_podcast_episodes")
    async def test_rss_no_author_in_channel(
        self, mock_get_episodes, mock_fetch_podcasts, client: AsyncClient
    ):
        """Il channel NON deve avere <author> (non valido in RSS 2.0), solo managingEditor."""
        await create_admin_via_setup(client)
        _setup_mocks(mock_get_episodes, mock_fetch_podcasts)

        resp = await client.get("/podcast/42/rss", follow_redirects=False)
        root = ET.fromstring(resp.text)
        channel = root.find("channel")

        assert channel.find("author") is None, "Il channel non deve avere l'elemento <author>"
        managing = channel.find("managingEditor")
        assert managing is not None
        assert "@" in managing.text, "managingEditor deve contenere un'email"

    @patch("routes.api.fetch_podcasts")
    @patch("routes.api.get_podcast_episodes")
    async def test_rss_item_author_email_format(
        self, mock_get_episodes, mock_fetch_podcasts, client: AsyncClient
    ):
        """L'<author> degli item deve essere nel formato 'email (nome)' per RSS 2.0."""
        await create_admin_via_setup(client)
        _setup_mocks(mock_get_episodes, mock_fetch_podcasts)

        resp = await client.get("/podcast/42/rss", follow_redirects=False)
        root = ET.fromstring(resp.text)
        items = root.findall("channel/item")

        for item in items:
            author = item.find("author")
            if author is not None and author.text:
                assert author.text.startswith("podcast@ilpost.it ("), \
                    f"Author non nel formato 'email (nome)': {author.text}"

    @patch("routes.api.fetch_podcasts")
    @patch("routes.api.get_podcast_episodes")
    async def test_rss_pubdate_has_timezone(
        self, mock_get_episodes, mock_fetch_podcasts, client: AsyncClient
    ):
        """Ogni pubDate deve essere RFC-822 con timezone."""
        await create_admin_via_setup(client)
        _setup_mocks(mock_get_episodes, mock_fetch_podcasts)

        resp = await client.get("/podcast/42/rss", follow_redirects=False)
        root = ET.fromstring(resp.text)
        items = root.findall("channel/item")

        dates_found = 0
        for item in items:
            pub_date = item.find("pubDate")
            if pub_date is not None and pub_date.text:
                dates_found += 1
                parsed = parsedate_tz(pub_date.text)
                assert parsed is not None, f"pubDate non parsabile: {pub_date.text}"
                assert parsed[-1] is not None, \
                    f"pubDate senza timezone: {pub_date.text}"
        # Almeno gli episodi con data devono avere pubDate
        assert dates_found >= 3

    @patch("routes.api.fetch_podcasts")
    @patch("routes.api.get_podcast_episodes")
    async def test_rss_enclosure_required_attrs(
        self, mock_get_episodes, mock_fetch_podcasts, client: AsyncClient
    ):
        """Ogni item deve avere enclosure con url, type e length."""
        await create_admin_via_setup(client)
        _setup_mocks(mock_get_episodes, mock_fetch_podcasts)

        resp = await client.get("/podcast/42/rss", follow_redirects=False)
        root = ET.fromstring(resp.text)
        items = root.findall("channel/item")

        assert len(items) == 5

        for item in items:
            title = item.find("title").text
            enclosure = item.find("enclosure")
            assert enclosure is not None, f"Manca enclosure in '{title}'"
            assert enclosure.get("url"), f"Manca enclosure url in '{title}'"
            assert enclosure.get("type") == "audio/mpeg", f"type errato in '{title}'"
            assert enclosure.get("length") is not None, f"Manca length in '{title}'"

    @patch("routes.api.fetch_podcasts")
    @patch("routes.api.get_podcast_episodes")
    async def test_rss_guid_unique(
        self, mock_get_episodes, mock_fetch_podcasts, client: AsyncClient
    ):
        """Ogni item deve avere un guid unico."""
        await create_admin_via_setup(client)
        _setup_mocks(mock_get_episodes, mock_fetch_podcasts)

        resp = await client.get("/podcast/42/rss", follow_redirects=False)
        root = ET.fromstring(resp.text)
        items = root.findall("channel/item")

        guids = set()
        for item in items:
            guid = item.find("guid")
            assert guid is not None
            assert guid.text
            assert guid.text not in guids, f"GUID duplicato: {guid.text}"
            guids.add(guid.text)

    @patch("routes.api.fetch_podcasts")
    @patch("routes.api.get_podcast_episodes")
    async def test_rss_special_chars_escaped(
        self, mock_get_episodes, mock_fetch_podcasts, client: AsyncClient
    ):
        """Caratteri speciali XML devono essere escaped correttamente."""
        await create_admin_via_setup(client)
        _setup_mocks(mock_get_episodes, mock_fetch_podcasts)

        resp = await client.get("/podcast/42/rss", follow_redirects=False)
        root = ET.fromstring(resp.text)
        items = root.findall("channel/item")

        special_item = [i for i in items if "speciali" in (i.find("title").text or "")]
        assert len(special_item) == 1

    @patch("routes.api.fetch_podcasts")
    @patch("routes.api.get_podcast_episodes")
    async def test_rss_no_googleplay_namespace(
        self, mock_get_episodes, mock_fetch_podcasts, client: AsyncClient
    ):
        """Il feed non deve usare il namespace googleplay (deprecato)."""
        await create_admin_via_setup(client)
        _setup_mocks(mock_get_episodes, mock_fetch_podcasts)

        resp = await client.get("/podcast/42/rss", follow_redirects=False)
        assert "google.com/schemas/play-podcasts" not in resp.text

    @patch("routes.api.fetch_podcasts")
    @patch("routes.api.get_podcast_episodes")
    async def test_rss_no_podcastindex_namespace(
        self, mock_get_episodes, mock_fetch_podcasts, client: AsyncClient
    ):
        """Il feed non deve usare il namespace podcastindex (non riconosciuto dai validatori)."""
        await create_admin_via_setup(client)
        _setup_mocks(mock_get_episodes, mock_fetch_podcasts)

        resp = await client.get("/podcast/42/rss", follow_redirects=False)
        assert "podcastindex.org" not in resp.text

    @patch("routes.api.fetch_podcasts")
    @patch("routes.api.get_podcast_episodes")
    async def test_rss_itunes_explicit_valid_value(
        self, mock_get_episodes, mock_fetch_podcasts, client: AsyncClient
    ):
        """itunes:explicit deve essere 'yes', 'no' o 'clean', non 'true'/'false'."""
        await create_admin_via_setup(client)
        _setup_mocks(mock_get_episodes, mock_fetch_podcasts)

        resp = await client.get("/podcast/42/rss", follow_redirects=False)
        root = ET.fromstring(resp.text)
        channel = root.find("channel")

        ns = {"itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd"}
        explicit = channel.find("itunes:explicit", ns)
        assert explicit is not None
        assert explicit.text in ("yes", "no", "clean", "true", "false"), \
            f"itunes:explicit deve essere un valore valido, trovato: {explicit.text}"

    @patch("routes.api.fetch_podcasts")
    @patch("routes.api.get_podcast_episodes")
    async def test_rss_itunes_category_not_obsolete(
        self, mock_get_episodes, mock_fetch_podcasts, client: AsyncClient
    ):
        """La categoria iTunes non deve essere obsoleta."""
        await create_admin_via_setup(client)
        _setup_mocks(mock_get_episodes, mock_fetch_podcasts)

        resp = await client.get("/podcast/42/rss", follow_redirects=False)
        root = ET.fromstring(resp.text)
        channel = root.find("channel")

        ns = {"itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd"}
        category = channel.find("itunes:category", ns)
        assert category is not None
        cat_text = category.get("text")
        # "News" da solo e' obsoleto, deve avere una sottocategoria
        subcategory = category.find("itunes:category", ns)
        assert subcategory is not None, \
            f"La categoria '{cat_text}' deve avere una sottocategoria"

    @patch("routes.api.fetch_podcasts")
    @patch("routes.api.get_podcast_episodes")
    async def test_rss_content_no_data_attributes(
        self, mock_get_episodes, mock_fetch_podcasts, client: AsyncClient
    ):
        """content:encoded non deve contenere attributi data-slate-* o data-encore-*."""
        await create_admin_via_setup(client)
        _setup_mocks(mock_get_episodes, mock_fetch_podcasts)

        resp = await client.get("/podcast/42/rss", follow_redirects=False)
        assert "data-slate-" not in resp.text, \
            "Trovati attributi data-slate-* nel feed"
        assert "data-encore-" not in resp.text, \
            "Trovati attributi data-encore-* nel feed"

    @patch("routes.api.fetch_podcasts")
    @patch("routes.api.get_podcast_episodes")
    async def test_rss_enclosure_url_percent_encoded(
        self, mock_get_episodes, mock_fetch_podcasts, client: AsyncClient
    ):
        """URL con caratteri non-ASCII (es. ellipsis …) devono essere percent-encoded."""
        await create_admin_via_setup(client)
        _setup_mocks(mock_get_episodes, mock_fetch_podcasts)

        resp = await client.get("/podcast/42/rss", follow_redirects=False)
        root = ET.fromstring(resp.text)
        items = root.findall("channel/item")

        for item in items:
            enclosure = item.find("enclosure")
            url = enclosure.get("url")
            # Nessun carattere non-ASCII nell'URL
            assert url.isascii(), f"URL contiene caratteri non-ASCII: {url}"

    @patch("routes.api.fetch_podcasts")
    @patch("routes.api.get_podcast_episodes")
    async def test_rss_content_no_style_tag(
        self, mock_get_episodes, mock_fetch_podcasts, client: AsyncClient
    ):
        """content:encoded non deve contenere tag <style>."""
        await create_admin_via_setup(client)
        _setup_mocks(mock_get_episodes, mock_fetch_podcasts)

        resp = await client.get("/podcast/42/rss", follow_redirects=False)
        # Il tag style potrebbe essere escaped in XML, controlliamo entrambe le forme
        assert "<style" not in resp.text.lower(), \
            "Trovato tag <style> nel feed"

    @patch("routes.api.fetch_podcasts")
    @patch("routes.api.get_podcast_episodes")
    async def test_rss_self_link_matches_request_url(
        self, mock_get_episodes, mock_fetch_podcasts, client: AsyncClient
    ):
        """L'atom:link self deve contenere il path del podcast."""
        await create_admin_via_setup(client)
        _setup_mocks(mock_get_episodes, mock_fetch_podcasts)

        resp = await client.get("/podcast/42/rss", follow_redirects=False)
        root = ET.fromstring(resp.text)
        channel = root.find("channel")

        ns = {"atom": "http://www.w3.org/2005/Atom"}
        atom_link = channel.find("atom:link[@rel='self']", ns)
        assert atom_link is not None
        href = atom_link.get("href")
        assert "/podcast/42/rss" in href

    @patch("routes.api.fetch_podcasts")
    @patch("routes.api.get_podcast_episodes")
    async def test_rss_token_url_self_link(
        self, mock_get_episodes, mock_fetch_podcasts, client: AsyncClient
    ):
        """Quando si accede via token, il self-link deve includere il token."""
        await create_admin_via_setup(client)
        _setup_mocks(mock_get_episodes, mock_fetch_podcasts)

        from database.database import AsyncSessionLocal
        from database.user_operations import get_user_by_username
        async with AsyncSessionLocal() as db:
            user = await get_user_by_username(db, "admin")
            token = user.rss_token

        resp = await client.get(f"/podcast/42/rss/{token}", follow_redirects=False)
        assert resp.status_code == 200

        root = ET.fromstring(resp.text)
        channel = root.find("channel")

        ns = {"atom": "http://www.w3.org/2005/Atom"}
        atom_link = channel.find("atom:link[@rel='self']", ns)
        href = atom_link.get("href")
        assert token in href, f"Il self-link deve contenere il token: {href}"

    @patch("routes.api.fetch_podcasts")
    @patch("routes.api.get_podcast_episodes")
    async def test_rss_content_encoded_no_cdata_escaped(
        self, mock_get_episodes, mock_fetch_podcasts, client: AsyncClient
    ):
        """content:encoded non deve contenere CDATA escaped (no &lt;![CDATA[)."""
        await create_admin_via_setup(client)
        _setup_mocks(mock_get_episodes, mock_fetch_podcasts)

        resp = await client.get("/podcast/42/rss", follow_redirects=False)
        assert "&lt;![CDATA[" not in resp.text, \
            "CDATA markers sono escaped - il contenuto HTML risulta invalido"


@pytest.mark.asyncio(loop_scope="session")
class TestRDFFeedValidation:
    """Valida la struttura del feed RDF generato."""

    @patch("routes.api.fetch_podcasts")
    @patch("routes.api.fetch_all_episodes")
    async def test_rdf_is_valid_xml(
        self, mock_fetch_all, mock_fetch_podcasts, client: AsyncClient
    ):
        await create_admin_via_setup(client)
        mock_fetch_podcasts.return_value = {"data": [MOCK_PODCAST_INFO]}
        mock_fetch_all.return_value = {"data": []}

        resp = await client.get("/podcast/42/rdf", follow_redirects=False)
        assert resp.status_code == 200
        assert "application/rdf+xml" in resp.headers["content-type"]
        ET.fromstring(resp.text)

    @patch("routes.api.fetch_podcasts")
    @patch("routes.api.fetch_all_episodes")
    async def test_rdf_feedparser_no_bozo(
        self, mock_fetch_all, mock_fetch_podcasts, client: AsyncClient
    ):
        await create_admin_via_setup(client)
        mock_fetch_podcasts.return_value = {"data": [MOCK_PODCAST_INFO]}
        mock_fetch_all.return_value = {
            "data": [
                {
                    "title": "Ep RDF",
                    "description": "Desc",
                    "content_html": "<p>HTML</p>",
                    "summary": "Riassunto",
                    "episode_raw_url": "https://cdn.example.com/ep.mp3",
                    "author": "Autore",
                    "image": "",
                    "share_url": "https://www.ilpost.it/ep",
                    "date": "2026-03-14T08:00:00+01:00",
                },
            ]
        }

        resp = await client.get("/podcast/42/rdf", follow_redirects=False)
        feed = feedparser.parse(resp.text)
        assert feed.bozo == 0, f"feedparser ha trovato errori: {feed.bozo_exception}"

    @patch("routes.api.fetch_podcasts")
    @patch("routes.api.fetch_all_episodes")
    async def test_rdf_no_cdata_escaped(
        self, mock_fetch_all, mock_fetch_podcasts, client: AsyncClient
    ):
        await create_admin_via_setup(client)
        mock_fetch_podcasts.return_value = {"data": [MOCK_PODCAST_INFO]}
        mock_fetch_all.return_value = {
            "data": [
                {
                    "title": "Ep",
                    "description": "Desc",
                    "content_html": "<p>HTML con <strong>tag</strong></p>",
                    "summary": "",
                    "episode_raw_url": "https://cdn.example.com/ep.mp3",
                    "author": "",
                    "share_url": "",
                    "date": "2026-03-14T08:00:00+01:00",
                },
            ]
        }

        resp = await client.get("/podcast/42/rdf", follow_redirects=False)
        assert "&lt;![CDATA[" not in resp.text
