Yandex music playlist backup tool
---

### Local setup
```shell
python3.13 -m venv venv
source venv/bin/activate
pip install -U --no-cache-dir poetry pip setuptools
poetry install
```

### Setup token
```shell
chrome https://oauth.yandex.ru/authorize?response_type=token&client_id=1a6990aa636648e9b2ef855fa7bec2fb
export YANDEX_MUSIC_TOKEN=%U_TOKEN_HERE%
```

### Run
```shell
python -m backup.refresh
```

TODOs
---
- up readme for local run
- check oauth token needed or not
- setup crontab
- describe project