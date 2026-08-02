"""Fallback track downloading from YouTube Music via yt-dlp."""
import asyncio
import logging
from pathlib import Path

from yt_dlp import YoutubeDL

from app.settings import app_settings

logger = logging.getLogger(__name__)


async def download_from_youtube(query: str, target: Path) -> bool:
    """Search YouTube Music for `query` and save the top hit as mp3 at `target`.

    Runs the blocking yt-dlp call in a worker thread. Returns True on success.
    """
    try:
        return await asyncio.to_thread(_download_sync, query, target)
    except Exception as exc:
        logger.warning(f'youtube fallback failed for {query!r}: {exc}')
        return False


def _ydl_options(target: Path) -> dict[str, object]:
    # yt-dlp appends the real extension, so hand it the path without one
    outtmpl = str(target.with_suffix(''))
    options: dict[str, object] = {
        # audio-only first, then any audio stream, then a progressive fallback
        'format': 'bestaudio/bestaudio*/best',
        'outtmpl': f'{outtmpl}.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'default_search': 'ytsearch1',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': str(app_settings.youtube_audio_quality),
        }],
    }
    if app_settings.youtube_cookies_file:
        options['cookiefile'] = str(app_settings.youtube_cookies_file)
    return options


def _download_sync(query: str, target: Path) -> bool:
    with YoutubeDL(_ydl_options(target)) as ydl:
        result = ydl.download([f'ytsearch1:{query}'])
    return int(result) == 0
