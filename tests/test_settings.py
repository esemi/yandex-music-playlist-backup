"""Tests for app.settings."""
from app.settings import Settings


def test_settings_default_dirs() -> None:
    settings = Settings()

    assert settings.logs_dir.name == 'logs'
    assert settings.tracks_dir.name == 'tracks'
    assert settings.playlists_dir.name == 'playlists'


def test_settings_env_override(monkeypatch) -> None:
    monkeypatch.setenv('logs_dir', '/custom/logs')

    settings = Settings()

    assert str(settings.logs_dir) == '/custom/logs'
