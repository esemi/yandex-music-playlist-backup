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
python -m app -u <username> [-x <proxy>] [-d]
```

| Flag | Long | Required | Description |
| --- | --- | --- | --- |
| `-u` | `--username` | yes | Username of the playlist owner whose likes are backed up |
| `-x` | `--proxy` | no | Proxy `host:port`, e.g. `127.0.0.1:1080` — use it when running outside Russia |
| `-d` | `--download` | no | Download liked tracks as mp3 into `<tracks_dir>/<username>/`, skipping files already on disk |

### Examples

```shell
# minimal run — back up likes of user `esemyon`
python -m app -u esemyon

# same, but through a SOCKS/HTTP proxy (required outside Russia)
python -m app -u esemyon -x 127.0.0.1:1080

# back up AND download new tracks as mp3
python -m app -u esemyon -x 127.0.0.1:1080 --download

# long-form flags
python -m app --username esemyon --proxy 127.0.0.1:1080
```

### Crontab example
```text
*/30 * * * * cd ~/development/yandex-music-playlist-backup && venv/bin/python -m app -u esemyon -x 127.0.0.1:1080 >> logs/refresh.log 2>&1
```

### TODO
[x] добавить выкачивание треков с яндекса (флаг --download)
[x] качать только то чего нет на диске
[ ] flock to docs
[ ] signal catch
[ ] [качать флаки](https://github.com/llistochek/yandex-music-downloader)
[ ] ускорить скачивание
[ ] добавить доки по рсинку на плеер
[ ] добавить выкачивание треков с ютюба
[ ] переделываем в десктоп апку?