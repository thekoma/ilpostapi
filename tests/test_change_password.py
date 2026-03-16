"""Tests for password change functionality."""
import pytest
from httpx import AsyncClient

from tests.conftest import create_admin_via_setup, login_client, create_user_via_admin


@pytest.mark.asyncio(loop_scope="session")
class TestChangePassword:
    async def test_change_password_page_requires_auth(self, client: AsyncClient):
        await create_admin_via_setup(client)
        await client.get("/auth/logout", follow_redirects=False)
        resp = await client.get("/auth/change-password", follow_redirects=False)
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["location"]

    async def test_change_password_page_renders(self, client: AsyncClient):
        await create_admin_via_setup(client)
        resp = await client.get("/auth/change-password")
        assert resp.status_code == 200
        assert "Cambia Password" in resp.text

    async def test_change_password_success(self, client: AsyncClient):
        await create_admin_via_setup(client)
        resp = await client.post(
            "/auth/change-password",
            data={
                "old_password": "adminpass123",
                "new_password": "newadminpass456",
                "new_password_confirm": "newadminpass456",
            },
        )
        assert resp.status_code == 200
        assert "aggiornata con successo" in resp.text

        # Verify new password works
        await client.get("/auth/logout", follow_redirects=False)
        resp = await login_client(client, "admin", "newadminpass456")
        assert resp.status_code == 302

    async def test_change_password_wrong_old(self, client: AsyncClient):
        await create_admin_via_setup(client)
        resp = await client.post(
            "/auth/change-password",
            data={
                "old_password": "wrongoldpassword",
                "new_password": "newpass12345",
                "new_password_confirm": "newpass12345",
            },
        )
        assert resp.status_code == 200
        assert "non è corretta" in resp.text

    async def test_change_password_mismatch(self, client: AsyncClient):
        await create_admin_via_setup(client)
        resp = await client.post(
            "/auth/change-password",
            data={
                "old_password": "adminpass123",
                "new_password": "newpass12345",
                "new_password_confirm": "differentpass",
            },
        )
        assert resp.status_code == 200
        assert "non corrispondono" in resp.text

    async def test_change_password_too_short(self, client: AsyncClient):
        await create_admin_via_setup(client)
        resp = await client.post(
            "/auth/change-password",
            data={
                "old_password": "adminpass123",
                "new_password": "short",
                "new_password_confirm": "short",
            },
        )
        assert resp.status_code == 200
        assert "almeno 8" in resp.text
