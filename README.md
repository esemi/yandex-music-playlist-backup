Yandex music playlist backup tool
---

A small CLI that snapshots a Yandex Music user's **liked tracks** and keeps a versioned
history of them on disk, so you never silently lose a track that got removed from the
service (e.g. pulled by the label or region-locked).

On every run it:

1. fetches the current list of liked tracks for the given user via the Yandex Music API;
2. compares it against the previous snapshot stored in `playlists/<username>.csv`;
3. records the delta — **added**, **deleted** and **restored** tracks — logging each change.

Deletions are *soft*: a track that disappears from the likes is marked with `is_deleted`
instead of being dropped from the CSV, so the backup stays a complete, append-only history.
If a previously deleted track shows up again, it's flagged as restored. Run it on a cron
schedule (see below) to keep the backup fresh.

Each snapshot is a plain CSV (`track_id, artist, title, added_at, is_deleted`), easy to
grep, diff or import elsewhere. Service paths (logs / tracks / playlists dirs) are
configurable via `app/settings.py` (env vars or `.env`).

With `--download` the tool fetches new tracks at the best quality the Yandex
`get-file-info` endpoint offers, decrypting the encrypted stream. In practice that's
**lossless FLAC**, always stored as `.flac`: a plain `.flac` stream is written directly,
and FLAC-in-MP4 is transcoded out of its MP4 container into `.flac` (lossless — FLAC
stays FLAC, only the container changes) because some players handle a bare `.flac`
better. When the track has no lossless master, a high-bitrate **AAC** is kept as `.m4a`
(re-encoding lossy AAC into FLAC would only bloat it). Only if `get-file-info` yields
nothing usable does it fall back to the legacy **mp3 320** API, and tracks Yandex
reports as **unavailable** (pulled by the label, region-locked) fall back to **YouTube
Music** via `yt-dlp` — controlled by the `youtube_fallback` setting (on by default). So
the cascade is FLAC (`.flac`) / AAC (`.m4a`) → mp3 320 → YouTube. The `get-file-info`
path is enabled by `prefer_lossless` (on by default); lossless files are noticeably
larger. Both the FLAC-in-MP4 transcode and the YouTube fallback need `ffmpeg`.

Already-downloaded tracks are skipped regardless of format (`.flac`, `.m4a` or `.mp3`),
so old mp3 files are left untouched — re-fetching them in FLAC is a manual job.

### Local setup

Requires `ffmpeg` in `PATH` (for the FLAC-in-MP4 transcode and the YouTube mp3 fallback):

```shell
python3.14 -m venv venv
source venv/bin/activate
pip install -U poetry pip
poetry install
```

### Usage

```text
python -m app -u <username> [-x <proxy>] [-d] [-t <token>]
```

| Flag | Long | Required | Description |
| --- | --- | --- | --- |
| `-u` | `--username` | yes | Username of the playlist owner whose likes are backed up |
| `-x` | `--proxy` | no | Proxy `host:port`, e.g. `127.0.0.1:1080` — use it when running outside Russia |
| `-d` | `--download` | no | Download liked tracks as mp3 into `<tracks_dir>/<username>/`, skipping files already on disk |
| `-t` | `--token` | no | Yandex Music OAuth token. Overrides `YANDEX_TOKEN` from settings/`.env` (needed to read private likes) |

### Examples

```shell
# minimal run — back up likes of user `esemyon`
python -m app -u esemyon

# same, but through a SOCKS/HTTP proxy (required outside Russia)
python -m app -u esemyon -x 127.0.0.1:1080

# back up AND download new tracks as mp3
python -m app -u esemyon -x 127.0.0.1:1080 --download

# pass the OAuth token explicitly instead of putting it in .env
python -m app -u esemyon --token y0__xxxxxxxx --download

# long-form flags
python -m app --username esemyon --proxy 127.0.0.1:1080
```

### Crontab example

`flock -n` guarantees a single instance: if a previous run is still going, the new one exits immediately instead of piling up.

```text
*/30 * * * * cd ~/development/yandex-music-playlist-backup && flock -n logs/refresh.lock venv/bin/python -m app -u esemyon -x 127.0.0.1:1080 -d >> logs/refresh.log 2>&1
```

### Sync downloaded tracks to a player

Downloaded mp3 live in `tracks/<username>/`. Mirror that folder to a player
(phone, SD card, DAP) with `rsync`.

```shell
rsync -av --partial tracks/esemyon/ /media/esemi/PLAYER/Music/esemyon/
```

`--delete` makes it a true mirror — tracks removed locally get removed on the
player too. Handy, but destructive, so double-check the target path first:

```shell
rsync -av --delete --partial tracks/esemyon/ /media/esemi/PLAYER/Music/esemyon/
```

