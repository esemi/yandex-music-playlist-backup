Yandex music playlist backup tool
---

### Local setup
```shell
python3.15 -m venv venv
source venv/bin/activate
pip install -U --no-cache-dir poetry pip
poetry install
```

### Usage

```text
python -m app -u <username> [-x <proxy>]
```

| Flag | Long | Required | Description |
| --- | --- | --- | --- |
| `-u` | `--username` | yes | Username of the playlist owner whose likes are backed up |
| `-x` | `--proxy` | no | Proxy `host:port`, e.g. `127.0.0.1:1080` — use it when running outside Russia |

### Examples

```shell
# minimal run — back up likes of user `esemyon`
python -m app -u esemyon

# same, but through a SOCKS/HTTP proxy (required outside Russia)
python -m app -u esemyon -x 127.0.0.1:1080

# long-form flags
python -m app --username esemyon --proxy 127.0.0.1:1080
```

### Crontab example
```text
*/30 * * * * cd ~/development/yandex-music-playlist-backup && venv/bin/python -m app -u esemyon -x 127.0.0.1:1080 >> logs/refresh.log 2>&1
```

### TODO
[x] сетингсы
[ ] линтеры
[ ] тесты
[ ] норм описание в ридми
[ ] добавить выкачивание треков с яндекса
[ ] добавить выкачивание треков с ютюба
[ ] качать только то чего нет на диске
[ ] добавить доки по рсинку на плеер
[ ] переделываем в десктоп апку?