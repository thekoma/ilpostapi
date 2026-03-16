"""Tests for favorites functionality."""
import pytest
from httpx import AsyncClient

from tests.conftest import create_admin_via_setup, login_client, create_user_via_admin


@pytest.mark.asyncio(loop_scope="session")
class TestFavoriteOperations:
    """Test CRUD operations on favorites."""

    async def test_get_favorites_empty(self, db_session):
        from database.user_operations import create_user
        from database.favorite_operations import get_user_favorites

        user = await create_user(db_session, username="favuser", email="fav@test.com", password="pass1234")
        favorites = await get_user_favorites(db_session, user.id)
        assert favorites == []

    async def test_add_favorite(self, db_session):
        from database.user_operations import create_user
        from database.favorite_operations import add_favorite, get_user_favorites

        user = await create_user(db_session, username="favuser2", email="fav2@test.com", password="pass1234")
        result = await add_favorite(db_session, user.id, 42)
        assert result is True

        favorites = await get_user_favorites(db_session, user.id)
        assert 42 in favorites

    async def test_add_favorite_duplicate(self, db_session):
        from database.user_operations import create_user
        from database.favorite_operations import add_favorite

        user = await create_user(db_session, username="favuser3", email="fav3@test.com", password="pass1234")
        await add_favorite(db_session, user.id, 42)
        result = await add_favorite(db_session, user.id, 42)
        assert result is False

    async def test_remove_favorite(self, db_session):
        from database.user_operations import create_user
        from database.favorite_operations import add_favorite, remove_favorite, get_user_favorites

        user = await create_user(db_session, username="favuser4", email="fav4@test.com", password="pass1234")
        await add_favorite(db_session, user.id, 42)
        result = await remove_favorite(db_session, user.id, 42)
        assert result is True

        favorites = await get_user_favorites(db_session, user.id)
        assert 42 not in favorites

    async def test_remove_favorite_not_exists(self, db_session):
        from database.user_operations import create_user
        from database.favorite_operations import remove_favorite

        user = await create_user(db_session, username="favuser5", email="fav5@test.com", password="pass1234")
        result = await remove_favorite(db_session, user.id, 999)
        assert result is False

    async def test_is_favorite(self, db_session):
        from database.user_operations import create_user
        from database.favorite_operations import add_favorite, is_favorite

        user = await create_user(db_session, username="favuser6", email="fav6@test.com", password="pass1234")
        assert await is_favorite(db_session, user.id, 42) is False
        await add_favorite(db_session, user.id, 42)
        assert await is_favorite(db_session, user.id, 42) is True

    async def test_multiple_favorites(self, db_session):
        from database.user_operations import create_user
        from database.favorite_operations import add_favorite, get_user_favorites

        user = await create_user(db_session, username="favuser7", email="fav7@test.com", password="pass1234")
        await add_favorite(db_session, user.id, 1)
        await add_favorite(db_session, user.id, 2)
        await add_favorite(db_session, user.id, 3)

        favorites = await get_user_favorites(db_session, user.id)
        assert set(favorites) == {1, 2, 3}

    async def test_favorites_per_user(self, db_session):
        """Ogni utente ha i suoi preferiti separati."""
        from database.user_operations import create_user
        from database.favorite_operations import add_favorite, get_user_favorites

        user1 = await create_user(db_session, username="favuserA", email="favA@test.com", password="pass1234")
        user2 = await create_user(db_session, username="favuserB", email="favB@test.com", password="pass1234")
        await add_favorite(db_session, user1.id, 10)
        await add_favorite(db_session, user2.id, 20)

        assert await get_user_favorites(db_session, user1.id) == [10]
        assert await get_user_favorites(db_session, user2.id) == [20]


@pytest.mark.asyncio(loop_scope="session")
class TestFavoritesAPI:
    """Test API endpoints for favorites."""

    async def test_get_favorites_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/favorites", follow_redirects=False)
        assert resp.status_code == 302

    async def test_toggle_favorite_add(self, client: AsyncClient):
        await create_admin_via_setup(client)
        resp = await client.post("/api/favorites/42")
        assert resp.status_code == 200
        assert resp.json()["favorited"] is True

    async def test_toggle_favorite_remove(self, client: AsyncClient):
        await create_admin_via_setup(client)
        # Aggiungi
        await client.post("/api/favorites/42")
        # Rimuovi
        resp = await client.post("/api/favorites/42")
        assert resp.status_code == 200
        assert resp.json()["favorited"] is False

    async def test_get_favorites_list(self, client: AsyncClient):
        await create_admin_via_setup(client)
        await client.post("/api/favorites/10")
        await client.post("/api/favorites/20")
        resp = await client.get("/api/favorites")
        assert resp.status_code == 200
        data = resp.json()
        assert 10 in data["favorites"]
        assert 20 in data["favorites"]

    async def test_toggle_favorite_requires_auth(self, client: AsyncClient):
        resp = await client.post("/api/favorites/42", follow_redirects=False)
        assert resp.status_code == 302


@pytest.mark.asyncio(loop_scope="session")
class TestOPML:
    """Test OPML generation."""

    async def test_opml_invalid_token(self, client: AsyncClient):
        resp = await client.get("/api/opml/invalid-token")
        assert resp.status_code == 403

    async def test_opml_generate_all(self):
        """Testa la generazione OPML con tutti i podcast."""
        from routes.api import _generate_opml

        podcasts = [
            {"id": 1, "title": "Podcast Uno"},
            {"id": 2, "title": "Podcast Due"},
        ]
        opml = _generate_opml(podcasts, "test-token-123", False, "https://app.example.com")
        assert "<opml" in opml
        assert "ilPost Podcasts" in opml
        assert "Podcast Uno" in opml
        assert "Podcast Due" in opml
        assert "test-token-123" in opml
        assert "https://app.example.com/podcast/" in opml
        assert "Preferiti" not in opml

    async def test_opml_generate_favorites_only(self):
        """Testa la generazione OPML solo preferiti."""
        from routes.api import _generate_opml

        podcasts = [{"id": 1, "title": "Preferito"}]
        opml = _generate_opml(podcasts, "token-abc", True, "https://app.example.com")
        assert "Preferiti" in opml
        assert "Preferito" in opml
        assert "token-abc" in opml

    async def test_opml_empty(self):
        """OPML con lista vuota."""
        from routes.api import _generate_opml

        opml = _generate_opml([], "token-xyz", False, "https://app.example.com")
        assert "<opml" in opml
        assert "</opml>" in opml

    async def test_opml_escapes_special_chars(self):
        """Testa che i caratteri speciali vengano escapati."""
        from routes.api import _generate_opml

        podcasts = [{"id": 1, "title": 'Podcast "Con & Caratteri <Speciali>'}]
        opml = _generate_opml(podcasts, "token", False, "https://app.example.com")
        assert "&amp;" in opml
        assert "&lt;" in opml
        assert "&gt;" in opml

    async def test_opml_uses_request_base_url(self):
        """Verifica che l'OPML usi l'URL del reverse proxy, non BASE_URL."""
        from routes.api import _generate_opml

        podcasts = [{"id": 1, "title": "Test"}]
        opml = _generate_opml(podcasts, "tok", False, "https://podcasts.mydomain.com")
        assert "https://podcasts.mydomain.com/podcast/1/rss/tok" in opml
