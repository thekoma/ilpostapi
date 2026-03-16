"""Tests for admin user management routes."""
import pytest
from httpx import AsyncClient

from tests.conftest import create_admin_via_setup, login_client, create_user_via_admin


@pytest.mark.asyncio(loop_scope="session")
class TestAdminAccess:
    async def test_admin_page_requires_auth(self, client: AsyncClient):
        await create_admin_via_setup(client)
        await client.get("/auth/logout", follow_redirects=False)
        resp = await client.get("/admin/users", follow_redirects=False)
        assert resp.status_code == 302
        assert "/auth/login" in resp.headers["location"]

    async def test_admin_page_requires_admin_role(self, client: AsyncClient):
        await create_admin_via_setup(client)
        # Create a regular user
        await create_user_via_admin(client, "regularuser", "regular@test.com", "password123", "user")
        # Login as regular user
        await client.get("/auth/logout", follow_redirects=False)
        await login_client(client, "regularuser", "password123")
        resp = await client.get("/admin/users", follow_redirects=False)
        assert resp.status_code == 403

    async def test_admin_page_renders_for_admin(self, client: AsyncClient):
        await create_admin_via_setup(client)
        resp = await client.get("/admin/users")
        assert resp.status_code == 200
        assert "Gestione Utenti" in resp.text


@pytest.mark.asyncio(loop_scope="session")
class TestAdminCreateUser:
    async def test_create_user(self, client: AsyncClient):
        await create_admin_via_setup(client)
        resp = await create_user_via_admin(client, "newuser1", "new1@test.com", "password123", "user")
        assert resp.status_code == 302

        # Verify user appears in list
        resp = await client.get("/admin/users")
        assert "newuser1" in resp.text

    async def test_create_admin_user(self, client: AsyncClient):
        await create_admin_via_setup(client)
        resp = await create_user_via_admin(client, "newadmin", "newadmin@test.com", "password123", "admin")
        assert resp.status_code == 302

    async def test_create_user_duplicate_username(self, client: AsyncClient):
        await create_admin_via_setup(client)
        await create_user_via_admin(client, "dupuser", "dup1@test.com", "password123")
        resp = await client.post(
            "/admin/users/create",
            data={
                "username": "dupuser",
                "email": "dup2@test.com",
                "password": "password123",
                "role": "user",
            },
        )
        assert resp.status_code == 200
        assert "gia in uso" in resp.text

    async def test_create_user_duplicate_email(self, client: AsyncClient):
        await create_admin_via_setup(client)
        await create_user_via_admin(client, "emaildup1", "samemail@test.com", "password123")
        resp = await client.post(
            "/admin/users/create",
            data={
                "username": "emaildup2",
                "email": "samemail@test.com",
                "password": "password123",
                "role": "user",
            },
        )
        assert resp.status_code == 200
        assert "gia in uso" in resp.text

    async def test_create_user_short_password(self, client: AsyncClient):
        await create_admin_via_setup(client)
        resp = await client.post(
            "/admin/users/create",
            data={
                "username": "shortpw",
                "email": "shortpw@test.com",
                "password": "short",
                "role": "user",
            },
        )
        assert resp.status_code == 200
        assert "almeno 8" in resp.text

    async def test_create_user_invalid_role_defaults_to_user(self, client: AsyncClient):
        await create_admin_via_setup(client)
        resp = await create_user_via_admin(client, "badrole", "badrole@test.com", "password123", "superadmin")
        # Should succeed (role sanitized to "user")
        assert resp.status_code == 302

    async def test_regular_user_cannot_create_users(self, client: AsyncClient):
        await create_admin_via_setup(client)
        await create_user_via_admin(client, "normie", "normie@test.com", "password123", "user")
        await client.get("/auth/logout", follow_redirects=False)
        await login_client(client, "normie", "password123")
        resp = await client.post(
            "/admin/users/create",
            data={
                "username": "hacked",
                "email": "hacked@test.com",
                "password": "password123",
                "role": "admin",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 403


@pytest.mark.asyncio(loop_scope="session")
class TestAdminDeleteUser:
    async def test_delete_user(self, client: AsyncClient):
        await create_admin_via_setup(client)
        await create_user_via_admin(client, "deletable", "deletable@test.com", "password123")

        # Find the user's ID from the admin page
        resp = await client.get("/admin/users")
        assert "deletable" in resp.text

        # Get all users to find the ID
        from database.database import AsyncSessionLocal
        from database.user_operations import get_user_by_username

        async with AsyncSessionLocal() as db:
            user = await get_user_by_username(db, "deletable")
            user_id = user.id

        resp = await client.post(f"/admin/users/{user_id}/delete", follow_redirects=False)
        assert resp.status_code == 302

        # Verify user is gone
        resp = await client.get("/admin/users")
        assert "deletable" not in resp.text

    async def test_cannot_delete_self(self, client: AsyncClient):
        await create_admin_via_setup(client)

        from database.database import AsyncSessionLocal
        from database.user_operations import get_user_by_username

        async with AsyncSessionLocal() as db:
            admin = await get_user_by_username(db, "admin")
            admin_id = admin.id

        resp = await client.post(f"/admin/users/{admin_id}/delete")
        assert resp.status_code == 200
        assert "te stesso" in resp.text

    async def test_cannot_delete_primary_admin(self, client: AsyncClient):
        """User with id=1 cannot be deleted even by another admin."""
        await create_admin_via_setup(client)
        # Create second admin
        await create_user_via_admin(client, "admin2", "admin2@test.com", "password123", "admin")
        # Login as second admin
        await client.get("/auth/logout", follow_redirects=False)
        await login_client(client, "admin2", "password123")
        # Try to delete user id=1
        resp = await client.post("/admin/users/1/delete")
        assert resp.status_code == 200
        assert "admin principale" in resp.text

    async def test_delete_nonexistent_user(self, client: AsyncClient):
        await create_admin_via_setup(client)
        resp = await client.post("/admin/users/99999/delete", follow_redirects=False)
        assert resp.status_code == 404

    async def test_regular_user_cannot_delete(self, client: AsyncClient):
        await create_admin_via_setup(client)
        await create_user_via_admin(client, "nodelperm", "nodelperm@test.com", "password123", "user")
        await client.get("/auth/logout", follow_redirects=False)
        await login_client(client, "nodelperm", "password123")
        resp = await client.post("/admin/users/1/delete", follow_redirects=False)
        assert resp.status_code == 403
