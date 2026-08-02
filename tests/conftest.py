"""Shared fixtures for the test suite."""
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path

import pytest
from app import refresh
from app.refresh import Track
from pytest_mock import MockerFixture


@pytest.fixture(autouse=True)
def _reset_shutdown() -> Iterator[None]:
    """Keep the module-level shutdown flag clean between tests."""
    refresh._shutdown.clear()
    yield
    refresh._shutdown.clear()


@pytest.fixture(autouse=True)
def _no_network_youtube(mocker: MockerFixture) -> None:
    """Never hit the real YouTube in tests; opt back in per-test if needed."""
    mocker.patch('app.refresh.download_from_youtube', new=mocker.AsyncMock(return_value=False))


@pytest.fixture
def make_track() -> Callable[..., Track]:
    """Factory building a Track with sane defaults; override any field via kwargs."""
    def _make(
        track_id: str = '1',
        artist: str = 'Artist',
        title: str = 'Title',
        added_at: datetime | None = None,
        is_deleted: bool = False,
    ) -> Track:
        return Track(
            track_id=track_id,
            artist=artist,
            title=title,
            added_at=added_at or datetime(2026, 1, 1, 12, 0, 0),
            is_deleted=is_deleted,
        )
    return _make


@pytest.fixture
def playlists_dir(tmp_path: Path, mocker: MockerFixture) -> Path:
    """Point app_settings.playlists_dir at an isolated temp dir for the test."""
    mocker.patch('app.refresh.app_settings.playlists_dir', tmp_path)
    return tmp_path


@pytest.fixture
def tracks_dir(tmp_path: Path, mocker: MockerFixture) -> Path:
    """Point app_settings.tracks_dir at an isolated temp dir for the test."""
    mocker.patch('app.refresh.app_settings.tracks_dir', tmp_path)
    return tmp_path


@pytest.fixture
def make_yandex_track(mocker: MockerFixture) -> Callable[..., object]:
    """Factory for a mocked yandex_music Track (raw API object)."""
    def _make(
        track_id: str = '1',
        artist: str = 'Artist',
        title: str = 'Title',
        available: bool = True,
        track_type: str = 'music',
    ) -> object:
        codec_info = mocker.MagicMock()
        codec_info.codec = 'mp3'
        codec_info.bitrate_in_kbps = 192
        codec_info.download_async = mocker.AsyncMock()

        track = mocker.MagicMock()
        track.id = track_id
        track.title = title
        track.available = available
        track.type = track_type
        track.artists = [mocker.MagicMock()]
        track.artists[0].name = artist
        track.get_download_info_async = mocker.AsyncMock(return_value=[codec_info])
        return track
    return _make
