"""Tests for track downloading in app.refresh."""
from collections.abc import Callable
from pathlib import Path

import pytest
from app import refresh
from app.refresh import Track, _download_tracks, _save_tracks_to_csv, _track_filename
from pytest_mock import MockerFixture


@pytest.mark.parametrize(('artist', 'title', 'expected'), [
    ('Nirvana', 'Come as You Are', 'Nirvana - Come as You Are.mp3'),
    ('AC/DC', 'T.N.T', 'AC_DC - T.N.T.mp3'),
    ('a?b', 'c:d*e', 'a_b - c_d_e.mp3'),
])
def test_track_filename(artist: str, title: str, expected: str) -> None:
    result = _track_filename(artist, title)

    assert result == expected


def _seed_csv(csv_path: Path, make_track: Callable[..., Track], track_ids: list[str]) -> None:
    _save_tracks_to_csv([make_track(track_id=tid) for tid in track_ids], csv_path)


def _codec_info(track: object) -> object:
    """Reach into the mocked yandex Track for its single codec_info download stub."""
    return track.get_download_info_async.return_value[0]


async def test_download_tracks_downloads_new(
    make_track: Callable[..., Track],
    make_yandex_track: Callable[..., object],
    tracks_dir: Path,
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    csv_path = tmp_path / 'user.csv'
    _seed_csv(csv_path, make_track, ['1', '2'])
    raw = [make_yandex_track(track_id='1'), make_yandex_track(track_id='2', title='Other')]
    client = mocker.MagicMock()
    client.tracks = mocker.AsyncMock(return_value=raw)
    mocker.patch('app.refresh._interruptible_sleep')

    downloaded = await _download_tracks(client, owner_id='user', csv_path=csv_path)

    assert downloaded == 2
    assert _codec_info(raw[0]).download_async.call_count == 1
    assert _codec_info(raw[1]).download_async.call_count == 1


async def test_download_tracks_stops_on_shutdown(
    make_track: Callable[..., Track],
    make_yandex_track: Callable[..., object],
    tracks_dir: Path,
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    csv_path = tmp_path / 'user.csv'
    _seed_csv(csv_path, make_track, ['1', '2'])
    raw = [make_yandex_track(track_id='1'), make_yandex_track(track_id='2', title='Other')]
    client = mocker.MagicMock()
    client.tracks = mocker.AsyncMock(return_value=raw)
    mocker.patch('app.refresh._interruptible_sleep')
    refresh._shutdown.set()

    downloaded = await _download_tracks(client, owner_id='user', csv_path=csv_path)

    assert downloaded == 0
    assert _codec_info(raw[0]).download_async.call_count == 0


async def test_download_tracks_skips_existing(
    make_track: Callable[..., Track],
    make_yandex_track: Callable[..., object],
    tracks_dir: Path,
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    csv_path = tmp_path / 'user.csv'
    _seed_csv(csv_path, make_track, ['1'])
    raw = make_yandex_track(artist='Artist', title='Title')
    (tracks_dir / 'user').mkdir()
    (tracks_dir / 'user' / 'Artist - Title.mp3').write_bytes(b'')
    client = mocker.MagicMock()
    client.tracks = mocker.AsyncMock(return_value=[raw])
    mocker.patch('app.refresh._interruptible_sleep')

    downloaded = await _download_tracks(client, owner_id='user', csv_path=csv_path)

    assert downloaded == 0
    assert _codec_info(raw).download_async.call_count == 0


async def test_download_tracks_skips_unavailable(
    make_track: Callable[..., Track],
    make_yandex_track: Callable[..., object],
    tracks_dir: Path,
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    csv_path = tmp_path / 'user.csv'
    _seed_csv(csv_path, make_track, ['1'])
    raw = make_yandex_track(available=False)
    client = mocker.MagicMock()
    client.tracks = mocker.AsyncMock(return_value=[raw])
    mocker.patch('app.refresh._interruptible_sleep')

    downloaded = await _download_tracks(client, owner_id='user', csv_path=csv_path)

    assert downloaded == 0
    assert _codec_info(raw).download_async.call_count == 0


async def test_download_tracks_creates_dest_dir(
    make_track: Callable[..., Track],
    make_yandex_track: Callable[..., object],
    tracks_dir: Path,
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    csv_path = tmp_path / 'user.csv'
    _seed_csv(csv_path, make_track, ['1'])
    client = mocker.MagicMock()
    client.tracks = mocker.AsyncMock(return_value=[make_yandex_track()])
    mocker.patch('app.refresh._interruptible_sleep')

    await _download_tracks(client, owner_id='user', csv_path=csv_path)

    assert (tracks_dir / 'user').is_dir()


async def test_download_tracks_timeout_not_counted(
    make_track: Callable[..., Track],
    make_yandex_track: Callable[..., object],
    tracks_dir: Path,
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    from yandex_music.exceptions import TimedOutError

    csv_path = tmp_path / 'user.csv'
    _seed_csv(csv_path, make_track, ['1'])
    raw = make_yandex_track()
    _codec_info(raw).download_async = mocker.AsyncMock(side_effect=TimedOutError())
    client = mocker.MagicMock()
    client.tracks = mocker.AsyncMock(return_value=[raw])
    mocker.patch('app.refresh._interruptible_sleep')

    downloaded = await _download_tracks(client, owner_id='user', csv_path=csv_path)

    assert downloaded == 0
