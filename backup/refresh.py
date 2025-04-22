"""Module for backing up Yandex Music playlist tracks."""
import asyncio
import copy
import csv
import logging
import os
from dataclasses import dataclass
from datetime import datetime

from yandex_music import ClientAsync

PLAYLIST_ID = '3'
PLAYLIST_OWNER_ID = 'esemyon'

logger = logging.getLogger(__file__)


@dataclass
class Track:
    """Data class for track information."""
    track_id: str
    artist: str
    title: str
    added_at: datetime
    is_deleted: bool


async def main() -> None:
    """Main function."""
    token: str = os.getenv('YANDEX_MUSIC_TOKEN')
    if not token:
        raise ValueError('YANDEX_MUSIC_TOKEN environment variable is required')

    client = await ClientAsync(token).init()
    added_tracks, deleted_tracks = await _refresh_playlist(
        client,
        playlist_id=PLAYLIST_ID,
        owner_id=PLAYLIST_OWNER_ID,
    )

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
        playlist_id: str,
        owner_id: str,
        csv_path: str = 'tracks.csv',
) -> tuple[list[Track], list[Track]]:
    """Update tracks list with current playlist state.

    Args:
        client: Initialized Yandex Music async client
        playlist_id: ID of the playlist to fetch
        csv_path: Path to the CSV file

    Returns:
        Tuple of (added_tracks, deleted_tracks) lists
    """
    try:
        existing_tracks: list[Track] = _get_tracks_from_csv(csv_path)
    except RuntimeError:
        existing_tracks = []
    existing_tracks_by_id = {track.track_id: track for track in existing_tracks}
    logger.info('got {0} existing tracks'.format(len(existing_tracks)))

    # Get actual tracks from Yandex Music
    actual_tracks = await _get_playlist_tracks(client, playlist_id, owner_id)
    refreshed_tracks = copy.deepcopy(actual_tracks)
    logger.info('got {0} actual tracks'.format(len(actual_tracks)))

    if not existing_tracks:
        _save_tracks_to_csv(refreshed_tracks, csv_path)
        return refreshed_tracks, []

    # check deleted and restored
    for track in refreshed_tracks:
        if track.track_id not in existing_tracks_by_id:
            logger.info('track {0} found'.format(track.track_id))

        if track.track_id in existing_tracks_by_id and track.is_deleted:
            logger.info('track {0} restored'.format(track.track_id))
            track.deleted_at = None

    # # Create lookup of existing tracks
    #
    # # Find deleted tracks
    # deleted_tracks = []
    # for track_id, track in existing_tracks_by_id.items():
    #     if track_id not in actual_track_ids:
    #         track.deleted_at = datetime.now()
    #         deleted_tracks.append(track)
    #
    # # Add new tracks
    # added_tracks = []
    # for track in actual_tracks:
    #     if track.track_id not in existing_tracks_by_id:
    #         existing_tracks_by_id[track.track_id] = track
    #         added_tracks.append(track)
    #
    #
    # save_tracks_to_csv(refreshed_tracks, csv_path)
    # return added_tracks, deleted_tracks


async def _get_playlist_tracks(client: ClientAsync, playlist_id: str, owner_id: str) -> list[Track]:
    """Get tracks from Yandex Music playlist.

    Args:
        client: Initialized Yandex Music async client
        playlist_id: ID of the playlist to fetch (default is '3' for Liked tracks)

    Returns:
        List of Track objects from the playlist
    """
    playlist = await client.users_playlists(
        kind=playlist_id,
        user_id=owner_id,
    )
    if not playlist:
        raise RuntimeError(f'Failed to get playlist {playlist_id}')

    track_ids = [track.track_id for track in playlist.tracks]
    now = datetime.now()

    raw_tracks = await client.tracks(track_ids=track_ids)
    logger.info('got {0} tracks'.format(len(raw_tracks)))

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
    """Load tracks from CSV file.

    Args:
        csv_path: Path to the CSV file with tracks data.

    Returns:
        List of Track objects from the CSV file.
        Empty list if file doesn't exist.
    """
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
    """Save tracks to CSV file.

    Args:
        tracks: List of Track objects to save
        csv_path: Path to the CSV file
    """
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
    asyncio.run(main())
