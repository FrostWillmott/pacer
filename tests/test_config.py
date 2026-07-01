from __future__ import annotations

from app.config import Settings, get_settings


def test_consolidation_intervals_parses_comma_separated_string() -> None:
    settings = Settings(consolidation_intervals="3, 14, 45")  # type: ignore[arg-type]
    assert settings.consolidation_intervals == [3, 14, 45]


def test_consolidation_intervals_accepts_list_unchanged() -> None:
    settings = Settings(consolidation_intervals=[1, 2, 3])
    assert settings.consolidation_intervals == [1, 2, 3]


def test_database_url_builds_asyncpg_dsn() -> None:
    settings = Settings(
        postgres_user="u",
        postgres_password="p",  # noqa: S106
        postgres_db="d",
        postgres_host="h",
        postgres_port=1234,
    )
    assert settings.database_url == "postgresql+asyncpg://u:p@h:1234/d"


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()
