"""Module for backing up Yandex Music playlist tracks."""
import argparse
import asyncio
import csv
import logging
import os
from dataclasses import dataclass
from datetime import datetime

from yandex_music import ClientAsync, TracksList
from yandex_music.utils.request_async import Request

logger = logging.getLogger(__file__)


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
) -> None:
    """Main function."""
    request = Request(proxy_url=f'http://{proxy_server}') if proxy_server else None
    client = await ClientAsync(request=request).init()

    added_tracks, deleted_tracks = await _refresh_playlist(client, owner_id=playlist_owner)

    if added_tracks:
        logger.info('\nAdded tracks:')
        for track in added_tracks:
            logger.info(f'  + {track.artist} - {track.title}')

    if deleted_tracks:
        logger.info('\nDeleted tracks:')
        for track in deleted_tracks:
            logger.info(f'  - {track.artist} - {track.title}')

    if not (added_tracks or deleted_tracks):
        logger.info('No changes detected')


async def _refresh_playlist(
    client: ClientAsync,
    owner_id: str,
    csv_path: str = 'tracks.csv',
) -> tuple[list[Track], list[Track]]:
    try:
        existing_tracks: list[Track] = _get_tracks_from_csv(csv_path)
    except RuntimeError:
        existing_tracks = []
    existing_track_ids: set[str] = {track.track_id for track in existing_tracks}
    logger.debug('got {0} existing tracks'.format(len(existing_tracks)))

    # Get actual tracks from Yandex Music
    actual_tracks: list[Track] = await _get_liked_tracks(client, owner_id)
    actual_tracks_by_id = {track.track_id: track for track in actual_tracks}
    logger.debug('got {0} actual tracks'.format(len(actual_tracks)))

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
                logger.debug('track {0} restored'.format(exist_track.fullname))
                exist_track.is_deleted = False

        elif not exist_track.is_deleted:
            if not actual_track or actual_track.is_deleted:
                exist_track.is_deleted = True
                logger.debug('track {0} deleted'.format(exist_track.fullname))
                deleted_tracks.append(exist_track)

        refreshed_tracks.append(exist_track)

    added_tracks = []
    for actual_track in actual_tracks:
        if actual_track.track_id not in existing_track_ids:
            logger.debug('track {0} added'.format(actual_track.fullname))
            added_tracks.append(actual_track)
            refreshed_tracks.append(actual_track)

    _save_tracks_to_csv(refreshed_tracks)
    return added_tracks, deleted_tracks


async def _get_liked_tracks(client: ClientAsync, owner_id: str) -> list[Track]:
    likes: TracksList = await client.users_likes_tracks(
        user_id=owner_id,
    )
    if not likes:
        raise RuntimeError('Failed to get likes')

    now = datetime.now()

    raw_tracks = await client.tracks(track_ids=likes.tracks_ids)
    logger.debug('got {0} tracks'.format(len(raw_tracks)))

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


def _get_tracks_from_csv(csv_path: str = 'tracks.csv') -> list[Track]:
    if not os.path.exists(csv_path):
        raise RuntimeError(f'File {csv_path} not found.')

    with open(csv_path, mode='r', encoding='utf-8', newline='') as f:
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


def _save_tracks_to_csv(tracks: list[Track], csv_path: str = 'tracks.csv') -> None:
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


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)-8s %(message)s',  # noqa: WPS323
    )

    parser = argparse.ArgumentParser(description='Run Yandex Music likes backup.')
    parser.add_argument(
        '-u', '--username',
        required=True,
        type=str,
        help='Username of playlist owner',
    )
    parser.add_argument(
        '-x', '--proxy',
        required=False,
        type=str,
        default=None,
        help='Proxy server <example: 92.39.141.246:65056>',
    )

    args = parser.parse_args()
    asyncio.run(main(
        playlist_owner=args.username,
        proxy_server=args.proxy,
    ))
