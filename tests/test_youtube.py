"""Tests for YouTube fallback options in app.youtube."""
from pathlib import Path

from app.youtube import _ydl_options
from pytest_mock import MockerFixture


def _audio_pp(opts: dict[str, object]) -> dict[str, object]:
    return opts['postprocessors'][0]  # type: ignore[index]


def test_ydl_options_default_quality() -> None:
    opts = _ydl_options(Path('/tmp/track.mp3'))

    pp = _audio_pp(opts)
    assert pp['preferredcodec'] == 'mp3'
    assert pp['preferredquality'] == '320'


def test_ydl_options_quality_from_settings(mocker: MockerFixture) -> None:
    mocker.patch('app.youtube.app_settings.youtube_audio_quality', 256)

    opts = _ydl_options(Path('/tmp/track.mp3'))

    assert _audio_pp(opts)['preferredquality'] == '256'


def test_ydl_options_no_cookies_by_default(mocker: MockerFixture) -> None:
    mocker.patch('app.youtube.app_settings.youtube_cookies_file', None)

    opts = _ydl_options(Path('/tmp/track.mp3'))

    assert 'cookiefile' not in opts


def test_ydl_options_cookies_from_settings(mocker: MockerFixture) -> None:
    mocker.patch('app.youtube.app_settings.youtube_cookies_file', Path('/etc/cookies.txt'))

    opts = _ydl_options(Path('/tmp/track.mp3'))

    assert opts['cookiefile'] == '/etc/cookies.txt'
