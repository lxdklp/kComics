# 配置读写 bin/config.json
import json
import os

_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config.json")

DEFAULTS = {"api_url": "api.copy202601.com", "username": "", "token": "",
            "download_concurrency": 3,
            "export_merged": True,
            "export_chapters_per_book": 5,
            "export_rtl": True,
            "kindle_documents_dir": "/mnt/us/documents",
            "check_update": True}

# 读取配置
def load():
    try:
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    changed = False
    for k, v in DEFAULTS.items():
        if k not in data:
            data[k] = v
            changed = True
    if changed:
        try:
            with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass
    return data

# 写回配置
def save(data):
    """写回配置到 config.json."""
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

#  —————— 读取配置项 ——————
# 拷贝漫画 API
def get_api_host():
    return (load().get("api_url") or DEFAULTS["api_url"]).strip() or DEFAULTS["api_url"]
# 登录 Token
def get_token():
    return load().get("token") or ""
# 下载并发
def get_download_concurrency():
    try:
        return max(1, int(load().get("download_concurrency") or 5))
    except (TypeError, ValueError):
        return 5
# 是否合并章节
def get_export_merged():
    return bool(load().get("export_merged"))
# 每本书合并的章节数
def get_export_chapters_per_book():
    try:
        return max(1, int(load().get("export_chapters_per_book") or 5))
    except (TypeError, ValueError):
        return 5
# 是否向右翻页
def get_export_rtl():
    return bool(load().get("export_rtl"))
# 自动检查更新
def get_check_update():
    return bool(load().get("check_update"))

#  —————— 路径 ——————
# 下载目录
def get_downloads_dir():
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "downloads")
# 临时目录
def get_export_tmp_dir():
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "tmp")
# Kindle 书库目录
def get_kindle_documents_dir():
    return str(load().get("kindle_documents_dir") or "").strip()