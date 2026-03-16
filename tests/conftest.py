import os
import sys
import tempfile

# Set env vars BEFORE importing anything from the app
os.environ.setdefault("EMAIL", "test@test.com")
os.environ.setdefault("PASSWORD", "testpassword")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only")
os.environ.setdefault("BASE_URL", "http://testserver")

# Use a temp dir for DB so each test session gets a fresh one
_test_db_dir = tempfile.mkdtemp(prefix="ilpostapi_test_")
os.environ["DB_DIR"] = _test_db_dir

# Add src to path so imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import asyncio
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from database.database import engine, AsyncSessionLocal, init_db
from database.models import Base
from database.user_operations import create_user


@pytest.fixture(scope="session")
def event_loop():
    """Create a session-scoped event loop."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def setup_db():
    """Initialize the database once for the test session."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(loop_scope="session")
async def db_session(setup_db) -> AsyncGenerator[AsyncSession, None]:
    """Provide a clean database session for each test."""
    async with AsyncSessionLocal() as session:
        # Clean users table before each test
        from database.models import User
        from sqlalchemy import delete
        await session.execute(delete(User))
        await session.commit()
        yield session


@pytest_asyncio.fixture(loop_scope="session")
async def admin_user(db_session: AsyncSession):
    """Create an admin user for tests."""
    user = await create_user(
        db_session,
        username="testadmin",
        email="admin@test.com",
        password="adminpass123",
        role="admin",
    )
    return user


@pytest_asyncio.fixture(loop_scope="session")
async def regular_user(db_session: AsyncSession):
    """Create a regular user for tests."""
    user = await create_user(
        db_session,
        username="testuser",
        email="user@test.com",
        password="userpass123",
        role="user",
    )
    return user


@pytest_asyncio.fixture(loop_scope="session")
async def client(setup_db) -> AsyncGenerator[AsyncClient, None]:
    """Provide an async HTTP test client with a fresh DB for each test."""
    # Change to src dir so static files and templates are found
    original_cwd = os.getcwd()
    os.chdir(os.path.join(os.path.dirname(__file__), "..", "src"))

    from main import app

    # Reset DB tables for each test using this fixture
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac

    os.chdir(original_cwd)


async def login_client(client: AsyncClient, username: str, password: str):
    """Helper: login and return cookies."""
    response = await client.post(
        "/auth/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )
    return response


async def create_admin_via_setup(client: AsyncClient,
                                  username="admin", email="admin@test.com",
                                  password="adminpass123"):
    """Helper: create the first admin via the setup flow."""
    response = await client.post(
        "/auth/setup",
        data={
            "username": username,
            "email": email,
            "password": password,
            "password_confirm": password,
        },
        follow_redirects=False,
    )
    return response


async def create_user_via_admin(client: AsyncClient,
                                 username="newuser", email="new@test.com",
                                 password="password123", role="user"):
    """Helper: create a user via admin panel."""
    response = await client.post(
        "/admin/users/create",
        data={
            "username": username,
            "email": email,
            "password": password,
            "role": role,
        },
        follow_redirects=False,
    )
    return response
