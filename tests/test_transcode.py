"""Tests for FLAC-in-MP4 -> .flac transcoding (app.transcode).

These exercise the real ffmpeg binary against a tiny synthetic stream, so they're
skipped when ffmpeg isn't on PATH.
"""
import shutil
import subprocess
from pathlib import Path

import pytest
from app.transcode import transcode_m4a_to_flac

pytestmark = pytest.mark.skipif(
    shutil.which('ffmpeg') is None or shutil.which('ffprobe') is None,
    reason='ffmpeg/ffprobe not available',
)


def _make_flac(path: Path) -> None:
    """Render a 0.5s sine tone into a real .flac stream."""
    subprocess.run(
        [
            'ffmpeg', '-v', 'error', '-y',
            '-f', 'lavfi', '-i', 'sine=frequency=440:duration=0.5',
            '-c:a', 'flac',
            str(path),
        ],
        check=True, capture_output=True,
    )


def _probe_codec(path: Path) -> str:
    result = subprocess.run(
        [
            'ffprobe', '-v', 'error',
            '-select_streams', 'a:0',
            '-show_entries', 'stream=codec_name',
            '-of', 'csv=p=0',
            str(path),
        ],
        check=True, capture_output=True, text=True,
    )
    return result.stdout.strip()


def test_transcode_flac_to_flac(tmp_path: Path) -> None:
    src = tmp_path / 'flac.flac'
    _make_flac(src)
    dst = tmp_path / 'out.flac'

    assert transcode_m4a_to_flac(src, dst) is True
    assert dst.exists()
    # the output is a real, plain FLAC stream
    assert _probe_codec(dst) == 'flac'


def test_transcode_bad_source_returns_false(tmp_path: Path) -> None:
    src = tmp_path / 'garbage.m4a'
    src.write_bytes(b'not really an mp4')
    dst = tmp_path / 'out.flac'

    assert transcode_m4a_to_flac(src, dst) is False
    # a failed run must not leave a half-written target behind
    assert not dst.exists()
