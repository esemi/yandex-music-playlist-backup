Yandex music playlist backup tool
---

### Local setup
```shell
python3.13 -m venv venv
source venv/bin/activate
pip install -U --no-cache-dir poetry pip setuptools
poetry install
```

### Run
```shell
python -m refresh -u esemyon -x 92.39.141.246:65056
```


### Crontab example
```text 
*/30 * * * * cd ~/development/yandex-music-playlist-backup && venv/bin/python -m refresh -u esemyon -x 92.39.141.246:65056 >> refresh.log 2>&1


```