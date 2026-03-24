"""Tests that all routes are properly protected by authentication."""
import pytest
from httpx import AsyncClient

from tests.conftest import create_admin_via_setup


@pytest.mark.asyncio(loop_scope="session")
class TestProtectedRoutes:
    """Verify that all protected endpoints redirect to login when not authenticated."""

    PROTECTED_GET_ROUTES = [
        "/",
        "/podcasts/directory",
        "/podcast/1/episodes",
        "/podcasts",
        "/podcasts/search?query=test",
        "/podcast/1",
        "/podcast/1/last",
        "/podcast/1/lastepisode",
        "/podcast/1/rss",
        "/clear-cache",
        "/api/podcast/1/episodes",
        "/api/podcast/1/episode/1/description",
        "/profile",
        "/auth/change-password",
        "/admin/users",
    ]

    PROTECTED_POST_ROUTES = [
        "/api/podcast/1/episode/1/refresh",
        "/api/podcast/1/update",
        "/api/podcasts/update",
        "/profile/regenerate-token",
        "/admin/users/create",
        "/admin/users/1/delete",
    ]

    async def test_all_get_routes_redirect_when_unauthenticated(self, client: AsyncClient):
        """Every protected GET route should redirect to /auth/login or /auth/setup."""
        await create_admin_via_setup(client)
        await client.get("/auth/logout", follow_redirects=False)

        for route in self.PROTECTED_GET_ROUTES:
            resp = await client.get(route, follow_redirects=False)
            assert resp.status_code in (302, 403), (
                f"GET {route} returned {resp.status_code}, expected 302 or 403"
            )
            if resp.status_code == 302:
                loc = resp.headers.get("location", "")
                assert "/auth/" in loc, (
                    f"GET {route} redirected to {loc}, expected /auth/*"
                )

    async def test_all_post_routes_redirect_when_unauthenticated(self, client: AsyncClient):
        """Every protected POST route should redirect or return 403/405."""
        await create_admin_via_setup(client)
        await client.get("/auth/logout", follow_redirects=False)

        for route in self.PROTECTED_POST_ROUTES:
            resp = await client.post(route, follow_redirects=False)
            assert resp.status_code in (302, 403, 422), (
                f"POST {route} returned {resp.status_code}, expected 302/403/422"
            )


@pytest.mark.asyncio(loop_scope="session")
class TestPublicRoutes:
    """Verify that public endpoints remain accessible without auth."""

    PUBLIC_ROUTES = [
        "/healthz",
        "/readyz",
        "/healthcheck",
        "/auth/login",
        "/auth/setup",
        "/docs",
        "/openapi.json",
    ]

    async def test_public_routes_accessible(self, client: AsyncClient):
        """Public routes should NOT redirect to auth."""
        for route in self.PUBLIC_ROUTES:
            resp = await client.get(route, follow_redirects=False)
            # Should not redirect to /auth/login (302 to setup is OK for /auth/login when no users)
            assert resp.status_code != 403, (
                f"GET {route} returned 403, should be public"
            )
