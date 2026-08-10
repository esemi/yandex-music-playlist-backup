"""Transcoding FLAC-in-MP4 streams into a plain .flac container.

Yandex's lossless streams arrive as FLAC-in-MP4: lossless audio, but wrapped in an
`.m4a` container that some players handle worse than a bare `.flac`. We only ever call
this for *FLAC*-in-MP4 — that repack is lossless (FLAC stays FLAC, only the container
changes). AAC-in-MP4 is left as `.m4a`: re-encoding lossy AAC into FLAC just bloats the
file ~6x without recovering any quality.

`ffmpeg` must be on PATH. Note ffmpeg refuses a plain `-c:a copy` from MP4 into a FLAC
container ("Exactly one FLAC audio stream is required"), so we re-encode with
`-c:a flac` — still lossless since the source is already FLAC.
"""
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def transcode_m4a_to_flac(source: Path, target: Path) -> bool:
    """Repack a FLAC-in-MP4 `source` into a `.flac` `target` (lossless), keeping tags.

    Returns True on success. The caller decides what to do with `source` afterwards.
    """
    try:
        subprocess.run(
            [
                'ffmpeg', '-v', 'error', '-y',
                '-i', str(source),
                '-map', '0:a', '-c:a', 'flac',
                '-map_metadata', '0',
                str(target),
            ],
            capture_output=True, text=True, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        stderr = getattr(exc, 'stderr', '') or ''
        logger.warning(f'ffmpeg transcode failed for {source}: {exc} {stderr}'.strip())
        target.unlink(missing_ok=True)
        return False
    return True
