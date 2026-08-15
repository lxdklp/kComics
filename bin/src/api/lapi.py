# LAPI
import json
import ssl
import urllib.error
import urllib.request

UPDATE_URL = "https://api.lxdklp.top/v1/kcomics/get_version"
TIMEOUT = 8

class UpdateError(Exception):
    pass

# 获取 UA
def _user_agent():
    from kcomics import VERSION
    return f"kComics/{VERSION}"

# 检查更新
def check_update():
    req = urllib.request.Request(UPDATE_URL, headers={"User-Agent": _user_agent()})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT,
                                    context=ssl._create_unverified_context()) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        raise UpdateError(f"HTTP {e.code}")
    except OSError as e:
        raise UpdateError(f"{type(e).__name__}: {e}")
    try:
        data = json.loads(raw.decode("utf-8"))
        build = int(data[0])
    except (ValueError, TypeError, IndexError, KeyError):
        raise UpdateError(f"响应格式错误:{raw[:60]}")
    return build
