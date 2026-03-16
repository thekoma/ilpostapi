"""Tests for the initial setup flow and login/logout."""
import pytest
import pytest_asyncio
from httpx import AsyncClient

from tests.conftest import create_admin_via_setup, login_client


@pytest.mark.asyncio(loop_scope="session")
class TestSetupFlow:
    """Test the first-time admin setup flow."""

    async def test_root_redirects_to_setup_when_no_users(self, client: AsyncClient):
        resp = await client.get("/", follow_redirects=False)
        assert resp.status_code == 302
        assert "/auth/setup" in resp.headers["location"]

    async def test_login_redirects_to_setup_when_no_users(self, client: AsyncClient):
        resp = await client.get("/auth/login", follow_redirects=False)
        assert resp.status_code == 302
        assert "/auth/setup" in resp.headers["location"]

    async def test_setup_page_renders(self, client: AsyncClient):
        resp = await client.get("/auth/setup")
        assert resp.status_code == 200
        assert "Benvenuto" in resp.text or "setup" in resp.text.lower()

    async def test_setup_password_mismatch(self, client: AsyncClient):
        resp = await client.post(
            "/auth/setup",
            data={
                "username": "admin",
                "email": "admin@test.com",
                "password": "password123",
                "password_confirm": "differentpassword",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 200
        assert "non corrispondono" in resp.text

    async def test_setup_password_too_short(self, client: AsyncClient):
        resp = await client.post(
            "/auth/setup",
            data={
                "username": "admin",
                "email": "admin@test.com",
                "password": "short",
                "password_confirm": "short",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 200
        assert "almeno 8" in resp.text

    async def test_setup_creates_admin_and_redirects(self, client: AsyncClient):
        resp = await create_admin_via_setup(client)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/"

    async def test_setup_blocked_after_admin_created(self, client: AsyncClient):
        # First create admin
        await create_admin_via_setup(client)
        # Try setup again
        resp = await client.get("/auth/setup", follow_redirects=False)
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["location"]

    async def test_setup_post_blocked_after_admin_created(self, client: AsyncClient):
        await create_admin_via_setup(client)
        resp = await client.post(
            "/auth/setup",
            data={
                "username": "hacker",
                "email": "hacker@test.com",
                "password": "password123",
                "password_confirm": "password123",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["location"]


@pytest.mark.asyncio(loop_scope="session")
class TestLogin:
    """Test login/logout flows."""

    async def test_login_page_renders(self, client: AsyncClient):
        await create_admin_via_setup(client)
        # Need a new client without the session cookie from setup
        resp = await client.get("/auth/logout", follow_redirects=False)
        resp = await client.get("/auth/login")
        assert resp.status_code == 200
        assert "Accedi" in resp.text

    async def test_login_with_valid_credentials(self, client: AsyncClient):
        await create_admin_via_setup(client)
        await client.get("/auth/logout", follow_redirects=False)
        resp = await login_client(client, "admin", "adminpass123")
        assert resp.status_code == 302
        assert resp.headers["location"] == "/"

    async def test_login_with_email(self, client: AsyncClient):
        await create_admin_via_setup(client)
        await client.get("/auth/logout", follow_redirects=False)
        resp = await login_client(client, "admin@test.com", "adminpass123")
        assert resp.status_code == 302
        assert resp.headers["location"] == "/"

    async def test_login_with_wrong_password(self, client: AsyncClient):
        await create_admin_via_setup(client)
        await client.get("/auth/logout", follow_redirects=False)
        resp = await client.post(
            "/auth/login",
            data={"username": "admin", "password": "wrongpassword"},
        )
        assert resp.status_code == 200
        assert "non valide" in resp.text

    async def test_login_with_nonexistent_user(self, client: AsyncClient):
        await create_admin_via_setup(client)
        await client.get("/auth/logout", follow_redirects=False)
        resp = await client.post(
            "/auth/login",
            data={"username": "nobody", "password": "password123"},
        )
        assert resp.status_code == 200
        assert "non valide" in resp.text

    async def test_login_redirects_if_already_logged_in(self, client: AsyncClient):
        await create_admin_via_setup(client)
        # Already logged in from setup
        resp = await client.get("/auth/login", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/"

    async def test_logout(self, client: AsyncClient):
        await create_admin_via_setup(client)
        resp = await client.get("/auth/logout", follow_redirects=False)
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["location"]

    async def test_protected_page_after_logout(self, client: AsyncClient):
        await create_admin_via_setup(client)
        await client.get("/auth/logout", follow_redirects=False)
        resp = await client.get("/profile", follow_redirects=False)
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["location"]
