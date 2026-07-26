import os

BASE_URL = "http://m.gugu5.com"
MANGA_LIST_PATH = "/o/{manga_id}/"
DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), "downloads")
DB_PATH = os.path.join(os.path.dirname(__file__), "manhua.db")
REQUEST_TIMEOUT = 30
MANGA_PROXY = os.environ.get("MANGA_PROXY")  # socks5://127.0.0.1:10809 仅漫画请求走代理
