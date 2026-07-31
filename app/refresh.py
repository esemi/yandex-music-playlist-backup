"""Module for backing up Yandex Music playlist tracks."""
import asyncio
import contextlib
import csv
import logging
import os
import re
import signal
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from yandex_music import ClientAsync, TracksList
from yandex_music.exceptions import TimedOutError
from yandex_music.utils.request_async import Request

from app.settings import app_settings

logger = logging.getLogger(__name__)

_FILENAME_UNSAFE = re.compile(r'[\\/:*?"<>|]+')

_shutdown = asyncio.Event()


def _install_signal_handlers() -> None:
    """Ask the running loop to flip the shutdown flag on SIGINT/SIGTERM."""
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_shutdown, sig)
        except NotImplementedError:  # pragma: no cover - windows / no-loop-signal support
            signal.signal(sig, lambda *_, s=sig: _request_shutdown(s))


def _request_shutdown(sig: signal.Signals) -> None:
    logger.warning(f'received {signal.Signals(sig).name}, finishing gracefully')
    _shutdown.set()


def _track_filename(artist: str, title: str) -> str:
    """Build a filesystem-safe `<artist> - <title>.mp3` name."""
    raw = f'{artist} - {title}'
    safe = _FILENAME_UNSAFE.sub('_', raw).strip()
    return f'{safe}.mp3'


@dataclass
class Track:
    """Data class for track information."""
    track_id: str
    artist: str
    title: str
    added_at: datetime
    is_deleted: bool

    @property
    def fullname(self) -> str:
        return f'{self.artist}: {self.title}'


async def main(
    playlist_owner: str,
    proxy_server: str | None = None,  # if you are running outside from Russian-related countries
    download: bool = False,
) -> None:
    """Main function."""
    _install_signal_handlers()

    request = Request(proxy_url=f'http://{proxy_server}') if proxy_server else None
    client = await ClientAsync(request=request, token=app_settings.yandex_token).init()

    csv_path = app_settings.playlists_dir / f'{playlist_owner}.csv'

    logger.info('Sync started')
    added_tracks, deleted_tracks = await _refresh_playlist(client, owner_id=playlist_owner, csv_path=csv_path)

    if added_tracks:
        logger.info('Added tracks:')
        for track in added_tracks:
            logger.info(f'  + {track.artist} - {track.title}')

    if deleted_tracks:
        logger.info('Deleted tracks:')
        for track in deleted_tracks:
            logger.info(f'  - {track.artist} - {track.title}')

    if not (added_tracks or deleted_tracks):
        logger.info('No changes detected')

    logger.info('Sync completed')

    if download and not _shutdown.is_set():
        logger.info('Downloading started')
        downloaded = await _download_tracks(client, owner_id=playlist_owner, csv_path=csv_path)
        logger.info(f'Downloaded {downloaded} new track(s)')
        logger.info('Downloading completed')


async def _refresh_playlist(
    client: ClientAsync,
    owner_id: str,
    csv_path: Path,
) -> tuple[list[Track], list[Track]]:
    try:
        existing_tracks: list[Track] = _get_tracks_from_csv(csv_path)
    except RuntimeError:
        existing_tracks = []
    existing_track_ids: set[str] = {track.track_id for track in existing_tracks}
    logger.debug(f'got {len(existing_tracks)} existing tracks')

    # Get actual tracks from Yandex Music
    actual_tracks: list[Track] = await _get_liked_tracks(client, owner_id)
    actual_tracks_by_id = {track.track_id: track for track in actual_tracks}
    logger.debug(f'got {len(actual_tracks)} actual tracks')

    if not existing_tracks:
        logger.debug('Initial run')
        _save_tracks_to_csv(actual_tracks, csv_path)
        return actual_tracks, []

    refreshed_tracks = []
    deleted_tracks = []
    for exist_track in existing_tracks:
        actual_track = actual_tracks_by_id.get(exist_track.track_id)
        if exist_track.is_deleted:
            if actual_track and not actual_track.is_deleted:
                logger.debug(f'track {exist_track.fullname} restored')
                exist_track.is_deleted = False

        elif not actual_track or actual_track.is_deleted:
            exist_track.is_deleted = True
            logger.debug(f'track {exist_track.fullname} deleted')
            deleted_tracks.append(exist_track)

        refreshed_tracks.append(exist_track)

    added_tracks = []
    for actual_track in actual_tracks:
        if actual_track.track_id not in existing_track_ids:
            logger.debug(f'track {actual_track.fullname} added')
            added_tracks.append(actual_track)
            refreshed_tracks.append(actual_track)

    _save_tracks_to_csv(refreshed_tracks, csv_path)
    return added_tracks, deleted_tracks


async def _get_liked_tracks(client: ClientAsync, owner_id: str) -> list[Track]:
    likes: TracksList = await client.users_likes_tracks(
        user_id=owner_id,
    )
    if not likes:
        raise RuntimeError('Failed to get likes')

    now = datetime.now()

    raw_tracks = await client.tracks(track_ids=likes.tracks_ids)
    logger.debug(f'got {len(raw_tracks)} tracks')

    return [
        Track(
            track_id=str(track.id),
            artist=', '.join(artist.name for artist in track.artists),
            title=track.title,
            added_at=now,
            is_deleted=not track.available,
        )
        for track in raw_tracks
    ]


async def _download_tracks(client: ClientAsync, owner_id: str, csv_path: Path) -> int:
    """Download liked tracks as mp3 into `dest_dir`, skipping ones already on disk.

    Returns the number of freshly downloaded files.
    """
    dest_dir = app_settings.tracks_dir / owner_id
    dest_dir.mkdir(exist_ok=True)

    existing_tracks: list[Track] = _get_tracks_from_csv(csv_path)
    logger.info(f'got {len(existing_tracks)} tracks from playlist')

    # load tracks by API
    raw_tracks = await client.tracks(track_ids=[
        track.track_id
        for track in existing_tracks
    ])

    downloaded = 0
    for track in raw_tracks:
        if _shutdown.is_set():
            logger.warning(f'shutdown requested, stopping after {downloaded} track(s)')
            break

        if not track.available:
            logger.info(f'skip unavailable {track.title}')
            continue

        artist = ', '.join(artist.name for artist in track.artists)
        target = dest_dir / _track_filename(artist, track.title)
        if target.exists():
            logger.debug(f'skip existing {target.name}')
            continue

        try:
            codec_info = (await track.get_download_info_async(timeout=10))[-1]
            logger.info(f'downloading {target} {codec_info.codec} {codec_info.bitrate_in_kbps}')
            await codec_info.download_async(str(target), timeout=25)
            logger.info('downloading success')

        except TimedOutError as exc:
            logger.warning(f'downloading failed {exc}')

        else:
            downloaded += 1

        await _interruptible_sleep(2)

    return downloaded


async def _interruptible_sleep(seconds: float) -> None:
    """Sleep, but wake up immediately if shutdown is requested."""
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(_shutdown.wait(), timeout=seconds)


def _get_tracks_from_csv(csv_path: Path) -> list[Track]:
    if not os.path.exists(csv_path):
        raise RuntimeError(f'File {csv_path} not found.')

    with open(csv_path, encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        return [
            Track(
                track_id=row['track_id'],
                artist=row['artist'],
                title=row['title'],
                added_at=datetime.fromisoformat(row['added_at']),
                is_deleted=bool(int(row['is_deleted']))
            )
            for row in reader
        ]


def _save_tracks_to_csv(tracks: list[Track], csv_path: Path) -> None:
    fieldnames = ['track_id', 'artist', 'title', 'added_at', 'is_deleted']

    with open(csv_path, mode='w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for track in sorted(tracks, key=lambda x: x.track_id):
            row = {
                'track_id': track.track_id,
                'artist': track.artist,
                'title': track.title,
                'added_at': track.added_at.isoformat(),
                'is_deleted': int(track.is_deleted),
            }
            writer.writerow(row)
