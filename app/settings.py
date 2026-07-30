"""Application settings."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Runtime configuration, overridable via env vars (prefix `YMB_`) or `.env`."""

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
    )

    logs_dir: Path = _ROOT_DIR / 'logs'
    tracks_dir: Path = _ROOT_DIR / 'tracks'
    playlists_dir: Path = _ROOT_DIR / 'playlists'


app_settings = Settings()
