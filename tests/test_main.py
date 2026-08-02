"""Tests for token resolution in app.refresh.main."""
from pathlib import Path

from app.refresh import main
from pytest_mock import MockerFixture


def _patch_main_deps(mocker: MockerFixture) -> MockerFixture:
    """Stub out everything main() touches except client construction."""
    mocker.patch('app.refresh._install_signal_handlers')
    client = mocker.MagicMock()
    client.init = mocker.AsyncMock(return_value=client)
    client_cls = mocker.patch('app.refresh.ClientAsync', return_value=client)
    mocker.patch('app.refresh._refresh_playlist', return_value=([], []))
    return client_cls


async def test_main_cli_token_overrides_settings(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    mocker.patch('app.refresh.app_settings.playlists_dir', tmp_path)
    mocker.patch('app.refresh.app_settings.yandex_token', 'from-settings')
    client_cls = _patch_main_deps(mocker)

    await main(playlist_owner='user', token='from-cli')

    assert client_cls.call_args.kwargs['token'] == 'from-cli'


async def test_main_falls_back_to_settings_token(
    tmp_path: Path,
    mocker: MockerFixture,
) -> None:
    mocker.patch('app.refresh.app_settings.playlists_dir', tmp_path)
    mocker.patch('app.refresh.app_settings.yandex_token', 'from-settings')
    client_cls = _patch_main_deps(mocker)

    await main(playlist_owner='user')

    assert client_cls.call_args.kwargs['token'] == 'from-settings'
