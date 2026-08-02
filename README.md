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

### Local setup
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

### TODO
[ ] добавить доки по рсинку на плеер
[ ] добавить выкачивание не найденных треков с ютуба
[ ] [качать флаки](https://github.com/llistochek/yandex-music-downloader)
[ ] переделываем в десктоп апку?