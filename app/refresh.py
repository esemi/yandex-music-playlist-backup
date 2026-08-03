"""Module for backing up Yandex Music playlist tracks."""
import asyncio
import csv
import logging
import os
import re
import signal
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from yandex_music import ClientAsync, TracksList
from yandex_music import Track as YandexTrack
from yandex_music.exceptions import NetworkError, TimedOutError
from yandex_music.utils.request_async import Request

from app.settings import app_settings
from app.yandex_lossless import download_best_encrypted
from app.youtube import download_from_youtube

logger = logging.getLogger(__name__)

_FILENAME_UNSAFE = re.compile(r'[\\/:*?"<>|]+')
# Most filesystems (ext4, apfs) cap a single filename at 255 bytes.
_FILENAME_MAX_BYTES = 255
# Every audio extension a track may already exist under, for skip-existing checks.
_AUDIO_EXTENSIONS = ('.flac', '.m4a', '.mp3')
_shutdown = asyncio.Event()


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
    token: str | None = None,  # CLI token takes priority over the one from settings
) -> None:
    """Main function."""
    _install_signal_handlers()

    request = Request(proxy_url=f'http://{proxy_server}') if proxy_server else None
    client = await ClientAsync(request=request, token=token or app_settings.yandex_token).init()

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

    if download:
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

    Downloads run concurrently, bounded by `download_concurrency`.
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

    semaphore = asyncio.Semaphore(app_settings.download_concurrency)
    results = await asyncio.gather(*[
        _download_one(client, track, dest_dir, semaphore)
        for track in raw_tracks
    ])
    return sum(results)


async def _download_one(
    client: ClientAsync,
    track: YandexTrack,
    dest_dir: Path,
    semaphore: asyncio.Semaphore,
) -> bool:
    """Download a single track; return True if a new file was written.

    Cascade: best `get-file-info` codec (FLAC / FLAC-in-MP4 / AAC) -> legacy mp3 320
    -> YouTube (for tracks Yandex reports as unavailable). The file extension follows
    whichever source won (`.flac` / `.m4a` / `.mp3`).
    """
    if _shutdown.is_set():
        return False

    if track.type != 'music':
        logger.info(f'skip not music {track.title} {track.type}')
        return False

    artist = ', '.join(artist.name for artist in track.artists)
    # Filename stem without extension; the winning source decides the real one. We
    # never touch the extension via Path.with_suffix — titles contain dots ("T.N.T").
    stem = _track_filename(artist, track.title, str(track.id))

    has_flac = any((dest_dir / f'{stem}{ext}').exists() for ext in ('.flac', '.m4a'))
    has_mp3 = (dest_dir / f'{stem}.mp3').exists()

    if has_flac:
        logger.info(f'skip existing flac for {artist} - {track.title}')
        return False

    if not track.available and has_mp3:
        logger.info(f'skip existing mp3 for unavailable {artist} - {track.title}')
        return False

    async with semaphore:
        if _shutdown.is_set():
            return False

        if not track.available:
            return await _download_unavailable(artist, track.title, dest_dir / f'{stem}.mp3')

        if await download_best_encrypted(client, str(track.id), dest_dir, stem, has_mp3):
            return True

        if has_mp3:
            return False

        logger.info(f'no get-file-info stream for {artist} - {track.title}, falling back to mp3 from yandex')
        return await _download_mp3(track, dest_dir / f'{stem}.mp3')


async def _download_mp3(track: YandexTrack, target: Path) -> bool:
    """Download the best available mp3 variant (highest bitrate) via the legacy API."""
    try:
        infos = await track.get_download_info_async(timeout=10)
        mp3_infos = [info for info in infos if info.codec == 'mp3']
        codec_info = max(mp3_infos or infos, key=lambda info: info.bitrate_in_kbps)
        logger.info(f'downloading {target} {codec_info.codec} {codec_info.bitrate_in_kbps}')
        await codec_info.download_async(str(target), timeout=25)
        logger.info('downloading success')
    except (TimedOutError, NetworkError) as exc:
        logger.warning(f'downloading failed {exc}')
        return False

    return True


async def _download_unavailable(
    artist: str,
    title: str,
    target: Path,
) -> bool:
    """Try YouTube Music for a track that Yandex reports as unavailable."""
    if not app_settings.youtube_fallback:
        logger.info(f'skip unavailable {title}')
        return False

    logger.info(f'unavailable on yandex, trying youtube: {artist} - {title}')
    return await download_from_youtube(f'{artist} {title}', target)


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


def _track_filename(artist: str, title: str, track_id: str) -> str:
    """Build a filesystem-safe filename *stem* `<artist> - <title> [<track_id>]`.

    Returns the name without extension — the caller appends `.flac` / `.m4a` / `.mp3`
    by concatenation (never `Path.with_suffix`, since titles contain dots like "T.N.T").

    The stem is truncated so the whole name — plus the longest audio extension — fits
    into the filesystem byte limit (compilations with dozens of artists easily blow
    past 255 bytes otherwise). The `[track_id]` tail is always kept intact, so
    truncated names stay unique.
    """
    raw = f'{artist} - {title}'
    safe = _FILENAME_UNSAFE.sub('_', raw).strip()

    max_ext_len = max(len(ext.encode('utf-8')) for ext in _AUDIO_EXTENSIONS)
    tail = f' [{track_id}]'
    budget = _FILENAME_MAX_BYTES - len(tail.encode('utf-8')) - max_ext_len
    encoded = safe.encode('utf-8')
    if len(encoded) > budget:
        # cut on a byte boundary, then drop a possibly broken trailing char
        safe = encoded[:budget].decode('utf-8', errors='ignore').rstrip()

    return f'{safe}{tail}'
