"""Shared fixtures for the test suite."""
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import pytest
from app.refresh import Track
from pytest_mock import MockerFixture


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
