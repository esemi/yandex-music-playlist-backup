"""Best-quality track downloading via the Yandex Music `get-file-info` endpoint.

The `yandex-music` client (3.0.0) only exposes the legacy `/download-info` endpoint,
which tops out at mp3/aac 320 kbps and never serves FLAC. Lossless (and the modern
AAC-in-MP4 streams) live behind `get-file-info` with a signed request and an AES-CTR
encrypted stream. We replicate that here, reusing the client's own request object (so
proxy/auth headers keep working) and the library's signing key.

On `quality=lossless` the server returns the best codec it can for the track:
`flac` / `flac-mp4` (both lossless), or an AAC variant, or `mp3`. Both lossless codecs
are stored as `.flac`: raw `flac` is already there, and `flac-mp4` is transcoded out of
its MP4 container (lossless — see app.transcode) because some players handle a bare
`.flac` better. Lossy AAC stays `.m4a`; repacking it into FLAC would only bloat it.
"""
import base64
import hashlib
import hmac
import logging
import os
import time
from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from yandex_music import ClientAsync
from yandex_music.exceptions import NetworkError, TimedOutError
from yandex_music.utils.sign_request import DEFAULT_SIGN_KEY

from app.transcode import transcode_m4a_to_flac

logger = logging.getLogger(__name__)

_GET_FILE_INFO_URL = 'https://api.music.yandex.net/get-file-info'
_TRANSPORTS = 'encraw'
_QUALITY_LOSSLESS = 'lossless'
# encraw streams are AES-128-CTR with a fixed all-zero 16-byte counter block.
_CTR_NONCE = bytes(16)

# codec (as returned by get-file-info) -> (final extension, is it lossless, needs transcode).
# `flac-mp4` is lossless FLAC inside an MP4 container: we store it as `.flac` by
# transcoding out of the container (lossless). Everything else is written as-is.
_CODEC_FORMATS: dict[str, tuple[str, bool, bool]] = {
    'flac': ('.flac', True, False),
    'flac-mp4': ('.flac', True, True),
    'aac': ('.m4a', False, False),
    'he-aac': ('.m4a', False, False),
    'aac-mp4': ('.m4a', False, False),
    'he-aac-mp4': ('.m4a', False, False),
    'mp3': ('.mp3', False, False),
}
# Codecs we ask for, in the order we prefer them (server still decides what it serves).
_CODECS = ','.join(_CODEC_FORMATS.keys())


async def download_best_encrypted(
    client: ClientAsync,
    track_id: str,
    dest_dir: Path,
    stem: str,
    has_mp3: bool,
    timeout: float = 25,
) -> Path | None:
    """Download `track_id` at the best codec `get-file-info` offers.

    The file is written to ``dest_dir / (stem + extension)`` where the extension is
    chosen from the codec the server returns (`.flac` / `.m4a` / `.mp3`). `stem` is the
    filename without extension (the caller keeps `_track_filename` as the single source
    of truth for naming). Note we append the extension by string concatenation, not
    ``Path.with_suffix`` — titles legitimately contain dots (e.g. "T.N.T").

    Returns the written Path on success, or None (rather than raising) when the
    endpoint gives nothing usable or the network hiccups, so the caller can fall back
    to the legacy mp3 API.
    """
    try:
        params = _build_get_file_info_params(track_id)
        result = await client.request.get(_GET_FILE_INFO_URL, params=params, timeout=timeout)
    except (TimedOutError, NetworkError) as exc:
        logger.warning(f'get-file-info failed for {track_id}: {exc}')
        return None

    download_info = (result or {}).get('download_info') or (result or {}).get('downloadInfo')
    if not download_info:
        logger.debug(f'no download info for {track_id}')
        return None

    codec = download_info.get('codec')
    urls = download_info.get('urls') or ([download_info['url']] if download_info.get('url') else [])
    key_hex = download_info.get('key')
    fmt = _CODEC_FORMATS.get(codec)
    if fmt is None or not urls or not key_hex:
        logger.debug(f'unusable get-file-info for {track_id} (codec={codec}, has_key={bool(key_hex)})')
        return None

    extension, lossless, needs_transcode = fmt
    if has_mp3 and extension == '.mp3':
        logger.debug('not found better than mp3 quality')
        return None

    try:
        encrypted = await client.request.retrieve(urls[0], timeout=timeout)
    except (TimedOutError, NetworkError) as exc:
        logger.warning(f'stream download failed for {track_id}: {exc}')
        return None

    decrypted = _decrypt_ctr(encrypted, key_hex)
    target = dest_dir / f'{stem}{extension}'

    if needs_transcode:
        # FLAC-in-MP4: write the raw MP4 to a temp file, then repack losslessly to .flac.
        tmp_m4a = dest_dir / f'{stem}.flacmp4.tmp'
        tmp_m4a.write_bytes(decrypted)
        try:
            if not transcode_m4a_to_flac(tmp_m4a, target):
                return None
        finally:
            tmp_m4a.unlink(missing_ok=True)
    else:
        target.write_bytes(decrypted)

    tag = 'lossless' if lossless else str(codec)
    logger.info(f'downloaded {tag} {target.name}')

    if extension != '.mp3' and (dest_dir / f'{stem}.mp3').exists():
        os.unlink(dest_dir / f'{stem}.mp3')

    return target


def _build_get_file_info_params(track_id: str) -> dict[str, str | int]:
    """Build the signed query params for `get-file-info`.

    The signature is HMAC-SHA256 over the concatenation of all param values (commas
    from the codec list stripped), base64-encoded, with the trailing char dropped.
    """
    params: dict[str, str | int] = {
        'ts': int(time.time()),
        'trackId': track_id,
        'quality': _QUALITY_LOSSLESS,
        'codecs': _CODECS,
        'transports': _TRANSPORTS,
    }
    message = ''.join(str(value) for value in params.values()).replace(',', '').encode('utf-8')
    digest = hmac.new(DEFAULT_SIGN_KEY.encode('utf-8'), message, hashlib.sha256).digest()
    params['sign'] = base64.b64encode(digest).decode('utf-8')[:-1]
    return params


def _decrypt_ctr(data: bytes, key_hex: str) -> bytes:
    """Decrypt an AES-128-CTR encraw stream. Key is a hex string, nonce is all zeros."""
    key = bytes.fromhex(key_hex)
    decryptor = Cipher(algorithms.AES(key), modes.CTR(_CTR_NONCE)).decryptor()
    return decryptor.update(data) + decryptor.finalize()
