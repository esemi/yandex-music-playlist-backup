"""Tests for track downloading in app.refresh."""
from collections.abc import Callable
from pathlib import Path

import pytest
from app import refresh
from app.refresh import Track, _download_tracks, _save_tracks_to_csv, _track_filename
from pytest_mock import MockerFixture


@pytest.mark.parametrize(('artist', 'title', 'expected'), [
    ('Nirvana', 'Come as You Are', 'Nirvana - Come as You Are [42].mp3'),
    ('AC/DC', 'T.N.T', 'AC_DC - T.N.T [42].mp3'),
    ('a?b', 'c:d*e', 'a_b - c_d_e [42].mp3'),
])
def test_track_filename(artist: str, title: str, expected: str) -> None:
    result = _track_filename(artist, title, '42')

    assert result == expected


def test_track_filename_truncates_long_name() -> None:
    result = _track_filename('Artist', 'x' * 500, '42')

    assert len(result.encode('utf-8')) <= 255
    assert result.endswith(' [42].mp3')


def test_track_filename_truncation_keeps_valid_utf8() -> None:
    result = _track_filename('Кино', 'Группа крови ' * 40, '42')

    assert len(result.encode('utf-8')) <= 255
    assert result.encode('utf-8').decode('utf-8') == result


def test_track_filename_unique_after_truncation() -> None:
    title = 'x' * 500

    name1 = _track_filename('Artist', title, '111')
    name2 = _track_filename('Artist', title, '222')

    assert name1 != name2


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

    downloaded = await _download_tracks(client, owner_id='user', csv_path=csv_path)

    assert downloaded == 2
    assert _codec_info(raw[0]).download_async.call_count == 1
    assert _codec_info(raw[1]).download_async.call_count == 1


async def test_download_tracks_respects_concurrency_limit(
    make_track: Callable[..., Track],
    make_yandex_track: Callable[..., object],
    tracks_dir: Path,
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    import asyncio

    mocker.patch('app.refresh.app_settings.download_concurrency', 2)
    csv_path = tmp_path / 'user.csv'
    ids = ['1', '2', '3', '4']
    _seed_csv(csv_path, make_track, ids)
    raw = [make_yandex_track(track_id=tid, title=f'T{tid}') for tid in ids]
    in_flight = 0
    peak = 0

    async def _slow_download(*_args: object, **_kwargs: object) -> None:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0)
        in_flight -= 1

    for track in raw:
        _codec_info(track).download_async = mocker.AsyncMock(side_effect=_slow_download)
    client = mocker.MagicMock()
    client.tracks = mocker.AsyncMock(return_value=raw)

    downloaded = await _download_tracks(client, owner_id='user', csv_path=csv_path)

    assert downloaded == 4
    assert peak <= 2


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
    (tracks_dir / 'user' / 'Artist - Title [1].mp3').write_bytes(b'')
    client = mocker.MagicMock()
    client.tracks = mocker.AsyncMock(return_value=[raw])

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

    downloaded = await _download_tracks(client, owner_id='user', csv_path=csv_path)

    assert downloaded == 0
    assert _codec_info(raw).download_async.call_count == 0


async def test_download_tracks_skips_podcast(
    make_track: Callable[..., Track],
    make_yandex_track: Callable[..., object],
    tracks_dir: Path,
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    csv_path = tmp_path / 'user.csv'
    _seed_csv(csv_path, make_track, ['1'])
    raw = make_yandex_track(track_type='podcast-episode')
    client = mocker.MagicMock()
    client.tracks = mocker.AsyncMock(return_value=[raw])

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

    downloaded = await _download_tracks(client, owner_id='user', csv_path=csv_path)

    assert downloaded == 0
