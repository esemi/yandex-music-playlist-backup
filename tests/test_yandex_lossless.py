"""Tests for the best-quality (get-file-info) download helpers."""
from pathlib import Path

from app.yandex_lossless import (
    _CTR_NONCE,
    _build_get_file_info_params,
    _decrypt_ctr,
    download_best_encrypted,
)
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from pytest_mock import MockerFixture


def _encrypt(plaintext: bytes, key_hex: str) -> bytes:
    encryptor = Cipher(algorithms.AES(bytes.fromhex(key_hex)), modes.CTR(_CTR_NONCE)).encryptor()
    return encryptor.update(plaintext) + encryptor.finalize()


def test_build_params_has_required_fields() -> None:
    params = _build_get_file_info_params('12345')

    assert params['trackId'] == '12345'
    assert params['quality'] == 'lossless'
    assert params['transports'] == 'encraw'
    assert 'flac' in str(params['codecs'])
    assert isinstance(params['ts'], int)
    assert isinstance(params['sign'], str) and params['sign']


def test_build_params_sign_is_deterministic_for_fixed_ts(mocker: MockerFixture) -> None:
    mocker.patch('app.yandex_lossless.time.time', return_value=1_700_000_000)

    first = _build_get_file_info_params('42')
    second = _build_get_file_info_params('42')

    assert first['sign'] == second['sign']
    # different track -> different signature
    assert _build_get_file_info_params('43')['sign'] != first['sign']


def test_decrypt_ctr_round_trip() -> None:
    key_hex = '00112233445566778899aabbccddeeff'
    plaintext = b'the quick brown fox jumps over the lazy dog' * 3

    assert _decrypt_ctr(_encrypt(plaintext, key_hex), key_hex) == plaintext


def _client_returning(mocker: MockerFixture, codec: str, ciphertext: bytes, key_hex: str) -> object:
    client = mocker.MagicMock()
    client.request.get = mocker.AsyncMock(return_value={
        'download_info': {'codec': codec, 'urls': ['https://host/stream'], 'key': key_hex},
    })
    client.request.retrieve = mocker.AsyncMock(return_value=ciphertext)
    return client


async def test_download_flac_writes_flac_extension(tmp_path: Path, mocker: MockerFixture) -> None:
    key_hex = '00112233445566778899aabbccddeeff'
    plaintext = b'FLAC-stream-bytes'
    client = _client_returning(mocker, 'flac', _encrypt(plaintext, key_hex), key_hex)

    result = await download_best_encrypted(client, '1', tmp_path, 'Artist - Title [1]', has_mp3=False)

    assert result == tmp_path / 'Artist - Title [1].flac'
    assert result is not None and result.read_bytes() == plaintext


async def test_download_flac_mp4_transcoded_to_flac(tmp_path: Path, mocker: MockerFixture) -> None:
    """FLAC-in-MP4 is lossless and gets repacked out of its MP4 container into a .flac."""
    key_hex = '00112233445566778899aabbccddeeff'
    client = _client_returning(mocker, 'flac-mp4', _encrypt(b'x', key_hex), key_hex)

    def _fake_transcode(source: Path, target: Path) -> bool:
        assert source.exists()  # the raw MP4 temp is on disk when we're called
        target.write_bytes(b'flac')
        return True

    transcode = mocker.patch('app.yandex_lossless.transcode_m4a_to_flac', side_effect=_fake_transcode)

    result = await download_best_encrypted(client, '1', tmp_path, 'Artist - Title [1]', has_mp3=False)

    assert result == tmp_path / 'Artist - Title [1].flac'
    assert result is not None and result.read_bytes() == b'flac'
    assert transcode.call_count == 1
    # the raw MP4 temp file must be cleaned up
    assert not (tmp_path / 'Artist - Title [1].flacmp4.tmp').exists()


async def test_download_flac_mp4_returns_none_on_transcode_failure(
    tmp_path: Path, mocker: MockerFixture,
) -> None:
    """A failed ffmpeg transcode falls through to None (caller drops to mp3 fallback)."""
    key_hex = '00112233445566778899aabbccddeeff'
    client = _client_returning(mocker, 'flac-mp4', _encrypt(b'x', key_hex), key_hex)
    mocker.patch('app.yandex_lossless.transcode_m4a_to_flac', return_value=False)

    result = await download_best_encrypted(client, '1', tmp_path, 'Artist - Title [1]', has_mp3=False)

    assert result is None
    assert not (tmp_path / 'Artist - Title [1].flacmp4.tmp').exists()


async def test_download_aac_writes_m4a(tmp_path: Path, mocker: MockerFixture) -> None:
    key_hex = '00112233445566778899aabbccddeeff'
    client = _client_returning(mocker, 'aac', _encrypt(b'x', key_hex), key_hex)

    result = await download_best_encrypted(client, '1', tmp_path, 'Artist - Title [1]', has_mp3=False)

    assert result == tmp_path / 'Artist - Title [1].m4a'


async def test_download_keeps_dots_in_title(tmp_path: Path, mocker: MockerFixture) -> None:
    """Dotted titles must not be mangled (regression: with_suffix ate 'T.N.T [id]')."""
    key_hex = '00112233445566778899aabbccddeeff'
    client = _client_returning(mocker, 'flac', _encrypt(b'x', key_hex), key_hex)

    result = await download_best_encrypted(client, '1', tmp_path, 'AC_DC - T.N.T [42]', has_mp3=False)

    assert result == tmp_path / 'AC_DC - T.N.T [42].flac'


async def test_download_returns_none_when_server_offers_only_mp3_and_mp3_exists(
    tmp_path: Path, mocker: MockerFixture,
) -> None:
    """If the best the server has is mp3 and we already hold an mp3, don't re-download."""
    key_hex = '00112233445566778899aabbccddeeff'
    client = _client_returning(mocker, 'mp3', _encrypt(b'x', key_hex), key_hex)

    result = await download_best_encrypted(client, '1', tmp_path, 'stem', has_mp3=True)

    assert result is None
    # stream must not even be fetched
    assert client.request.retrieve.call_count == 0


async def test_download_mp3_when_no_local_mp3(tmp_path: Path, mocker: MockerFixture) -> None:
    """Server-side mp3 is still downloaded when nothing is on disk yet."""
    key_hex = '00112233445566778899aabbccddeeff'
    plaintext = b'mp3-bytes'
    client = _client_returning(mocker, 'mp3', _encrypt(plaintext, key_hex), key_hex)

    result = await download_best_encrypted(client, '1', tmp_path, 'stem', has_mp3=False)

    assert result == tmp_path / 'stem.mp3'
    assert result is not None and result.read_bytes() == plaintext


async def test_download_lossless_removes_stale_mp3(tmp_path: Path, mocker: MockerFixture) -> None:
    """Upgrading an existing mp3 to lossless drops the old mp3 file."""
    key_hex = '00112233445566778899aabbccddeeff'
    client = _client_returning(mocker, 'flac', _encrypt(b'x', key_hex), key_hex)
    stale_mp3 = tmp_path / 'stem.mp3'
    stale_mp3.write_bytes(b'old')

    result = await download_best_encrypted(client, '1', tmp_path, 'stem', has_mp3=True)

    assert result == tmp_path / 'stem.flac'
    assert result is not None and result.exists()
    assert not stale_mp3.exists()


async def test_download_returns_none_for_unknown_codec(tmp_path: Path, mocker: MockerFixture) -> None:
    client = mocker.MagicMock()
    client.request.get = mocker.AsyncMock(return_value={
        'download_info': {'codec': 'weird', 'urls': ['https://host/s'], 'key': 'ab'},
    })
    client.request.retrieve = mocker.AsyncMock()

    result = await download_best_encrypted(client, '1', tmp_path, 'stem', has_mp3=False)

    assert result is None
    assert client.request.retrieve.call_count == 0


async def test_download_returns_none_on_empty_response(tmp_path: Path, mocker: MockerFixture) -> None:
    client = mocker.MagicMock()
    client.request.get = mocker.AsyncMock(return_value=None)

    assert await download_best_encrypted(client, '1', tmp_path, 'stem', has_mp3=False) is None


async def test_download_swallows_get_network_error(tmp_path: Path, mocker: MockerFixture) -> None:
    from yandex_music.exceptions import NetworkError

    client = mocker.MagicMock()
    client.request.get = mocker.AsyncMock(side_effect=NetworkError('boom'))

    assert await download_best_encrypted(client, '1', tmp_path, 'stem', has_mp3=False) is None


async def test_download_swallows_stream_timeout(tmp_path: Path, mocker: MockerFixture) -> None:
    from yandex_music.exceptions import TimedOutError

    client = mocker.MagicMock()
    client.request.get = mocker.AsyncMock(return_value={
        'download_info': {'codec': 'flac', 'urls': ['https://host/s'], 'key': 'ab'},
    })
    client.request.retrieve = mocker.AsyncMock(side_effect=TimedOutError())

    result = await download_best_encrypted(client, '1', tmp_path, 'stem', has_mp3=False)

    assert result is None
    assert not (tmp_path / 'stem.flac').exists()
