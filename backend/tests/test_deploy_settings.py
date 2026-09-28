from app.core.config import CAPACITOR_ORIGINS, Settings, with_driver


def test_cors_origins_include_website_and_capacitor():
    settings = Settings(
        _env_file=None,
        cors_origins_raw="https://pedagogue.app/, http://localhost:5173",
        website_url="https://www.pedagogue.app",
    )
    origins = settings.cors_origins
    assert "https://pedagogue.app" in origins
    assert "https://www.pedagogue.app" in origins
    assert "http://localhost:5173" in origins
    for origin in CAPACITOR_ORIGINS:
        assert origin in origins
    assert len(origins) == len(set(origins))


def test_capacitor_origins_can_be_switched_off():
    settings = Settings(_env_file=None, cors_origins_raw="https://pedagogue.app", allow_capacitor_origins=False)
    assert settings.cors_origins == ["https://pedagogue.app"]


def test_capacitor_origins_come_from_the_cors_env(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://pedagogue.app")
    monkeypatch.setenv("WEBSITE_URL", "https://pedagogue.app")
    origins = Settings(_env_file=None).cors_origins
    assert origins[0] == "https://pedagogue.app"
    assert "capacitor://localhost" in origins


def test_managed_postgres_urls_get_drivers(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://user:pw@db.internal:5432/piano")
    monkeypatch.delenv("ALEMBIC_DATABASE_URL", raising=False)
    settings = Settings(_env_file=None)
    assert settings.async_dsn == "postgresql+asyncpg://user:pw@db.internal:5432/piano"
    assert settings.sync_dsn == "postgresql+psycopg://user:pw@db.internal:5432/piano"


def test_explicit_driver_urls_are_kept():
    assert with_driver("postgresql+asyncpg://a@b/c", "asyncpg") == "postgresql+asyncpg://a@b/c"
    assert with_driver("sqlite:///x.db", "asyncpg") == "sqlite:///x.db"


async def test_capacitor_preflight_is_allowed():
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options(
            "/api/v1/auth/me",
            headers={"Origin": "capacitor://localhost", "Access-Control-Request-Method": "GET"},
        )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "capacitor://localhost"
