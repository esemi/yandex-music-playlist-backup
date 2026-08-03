"""Application settings."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file='.env',
    )

    logs_dir: Path = _ROOT_DIR / 'logs'
    tracks_dir: Path = _ROOT_DIR / 'tracks'
    playlists_dir: Path = _ROOT_DIR / 'playlists'

    yandex_token: str | None = None
    download_concurrency: int = 8

    youtube_fallback: bool = True
    youtube_audio_quality: int = 320
    youtube_cookies_file: Path | None = None  # Netscape cookies.txt for authed downloads from youtube


app_settings = Settings()
