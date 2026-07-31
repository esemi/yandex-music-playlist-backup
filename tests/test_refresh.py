"""Tests for the backup/diff logic in app.refresh."""
from collections.abc import Callable
from pathlib import Path

import pytest
from app.refresh import (
    Track,
    _get_tracks_from_csv,
    _refresh_playlist,
    _save_tracks_to_csv,
)
from pytest_mock import MockerFixture


def test_fullname(make_track: Callable[..., Track]) -> None:
    track = make_track(artist='Nirvana', title='Come as You Are')

    result = track.fullname

    assert result == 'Nirvana: Come as You Are'


def test_save_and_get_tracks_from_csv_roundtrip(
    make_track: Callable[..., Track],
    tmp_path: Path,
) -> None:
    tracks = [make_track(track_id='2', title='B'), make_track(track_id='1', title='A')]
    csv_path = tmp_path / 'roundtrip.csv'

    _save_tracks_to_csv(tracks, csv_path)
    restored = _get_tracks_from_csv(csv_path)

    assert [track.track_id for track in restored] == ['1', '2']
    assert restored[0].title == 'A'
    assert restored[1].title == 'B'


def test_save_tracks_to_csv_sorts_by_track_id(
    make_track: Callable[..., Track],
    tmp_path: Path,
) -> None:
    tracks = [make_track(track_id='3'), make_track(track_id='1'), make_track(track_id='2')]
    csv_path = tmp_path / 'sorted.csv'

    _save_tracks_to_csv(tracks, csv_path)
    restored = _get_tracks_from_csv(csv_path)

    assert [track.track_id for track in restored] == ['1', '2', '3']


def test_get_tracks_from_csv_not_found(tmp_path: Path) -> None:
    missing = tmp_path / 'nope.csv'

    with pytest.raises(RuntimeError):
        _get_tracks_from_csv(missing)


def _patch_liked(mocker: MockerFixture, tracks: list[Track]) -> None:
    mocker.patch('app.refresh._get_liked_tracks', return_value=tracks)


async def test_refresh_playlist_initial_run(
    make_track: Callable[..., Track],
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    csv_path = tmp_path / 'user.csv'
    actual = [make_track(track_id='1'), make_track(track_id='2')]
    _patch_liked(mocker, actual)
    client = mocker.MagicMock()

    added, deleted = await _refresh_playlist(client, owner_id='user', csv_path=csv_path)

    assert {track.track_id for track in added} == {'1', '2'}
    assert deleted == []
    assert csv_path.exists()


async def test_refresh_playlist_added(
    make_track: Callable[..., Track],
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    csv_path = tmp_path / 'user.csv'
    _save_tracks_to_csv([make_track(track_id='1')], csv_path)
    _patch_liked(mocker, [make_track(track_id='1'), make_track(track_id='2')])
    client = mocker.MagicMock()

    added, deleted = await _refresh_playlist(client, owner_id='user', csv_path=csv_path)

    assert [track.track_id for track in added] == ['2']
    assert deleted == []


async def test_refresh_playlist_deleted(
    make_track: Callable[..., Track],
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    csv_path = tmp_path / 'user.csv'
    _save_tracks_to_csv([make_track(track_id='1'), make_track(track_id='2')], csv_path)
    _patch_liked(mocker, [make_track(track_id='1')])
    client = mocker.MagicMock()

    added, deleted = await _refresh_playlist(client, owner_id='user', csv_path=csv_path)

    assert added == []
    assert [track.track_id for track in deleted] == ['2']


async def test_refresh_playlist_deleted_marks_is_deleted_in_csv(
    make_track: Callable[..., Track],
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    csv_path = tmp_path / 'user.csv'
    _save_tracks_to_csv([make_track(track_id='1')], csv_path)
    _patch_liked(mocker, [])
    client = mocker.MagicMock()

    await _refresh_playlist(client, owner_id='user', csv_path=csv_path)
    persisted = _get_tracks_from_csv(csv_path)

    assert len(persisted) == 1
    assert persisted[0].is_deleted is True


async def test_refresh_playlist_restored(
    make_track: Callable[..., Track],
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    csv_path = tmp_path / 'user.csv'
    _save_tracks_to_csv([make_track(track_id='1', is_deleted=True)], csv_path)
    _patch_liked(mocker, [make_track(track_id='1', is_deleted=False)])
    client = mocker.MagicMock()

    added, deleted = await _refresh_playlist(client, owner_id='user', csv_path=csv_path)
    persisted = _get_tracks_from_csv(csv_path)

    assert added == []
    assert deleted == []
    assert persisted[0].is_deleted is False


async def test_refresh_playlist_no_changes(
    make_track: Callable[..., Track],
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    csv_path = tmp_path / 'user.csv'
    _save_tracks_to_csv([make_track(track_id='1')], csv_path)
    _patch_liked(mocker, [make_track(track_id='1')])
    client = mocker.MagicMock()

    added, deleted = await _refresh_playlist(client, owner_id='user', csv_path=csv_path)

    assert added == []
    assert deleted == []
