# copymanga App API 参考 copymanga-downloader
import base64
import json
import os
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

import config

APP_VERSION = "2025.08.15"
UA = "COPY/3.0.0"
PLATFORM = "1"
REGION = "1"
WEBP = "1"

TIMEOUT = 8
socket.setdefaulttimeout(TIMEOUT)


class ApiError(Exception):
    pass

# 请求头
def _headers(token=""):
    headers = {
        "User-Agent": UA,
        "Accept": "application/json",
        "version": APP_VERSION,
        "platform": PLATFORM,
        "webp": WEBP,
        "region": REGION,
    }
    if token:
        headers["authorization"] = f"Token {token}"
    return headers

# 请求
def _fetch(request, timeout, ctx):
    with urllib.request.urlopen(request, timeout=timeout, context=ctx) as resp:
        return resp.read()

# 敏感值掩码
def _mask(value, keep=3):
    if not value:
        return "(无)"
    if len(value) <= keep + 3:
        return value[:keep] + "***"
    return value[:keep] + "***" + value[-2:]

# HTTP请求
def _do(url, body=None, headers=None, timeout=TIMEOUT, retries=3):
    req_headers = {"User-Agent": UA}
    if headers:
        req_headers.update(headers)
    method = "POST" if body is not None else "GET"
    data = body.encode() if isinstance(body, str) else body
    request = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    auth = req_headers.get("authorization", "")
    print(f"[API] {method} {url}")
    print(f"[API] 请求头: UA={req_headers.get('User-Agent')} "
            f"platform={req_headers.get('platform')} authorization={_mask(auth)}")
    if data:
        print(f"[API] 请求体: {data.decode('utf-8', 'replace')[:200]}")
    t0 = time.time()
    raw = None
    last_err = None
    for attempt in range(retries):
        try:
            raw = _fetch(request, timeout, ssl.create_default_context())
        except urllib.error.HTTPError as e:
            err_body = b""
            try:
                err_body = e.read()
            except OSError:
                pass
            text = err_body.decode("utf-8", "replace")
            print(f"[API] HTTP {e.code}: {text[:200]}")
            try:
                return json.loads(text)
            except ValueError:
                raise ApiError(f"HTTP {e.code}: {text[:120]}")
        except OSError as e:
            if attempt == 0:
                print(f"[API] 证书校验失败: {type(e).__name__}: {e},降级为不校验证书重试")
                try:
                    raw = _fetch(request, timeout, ssl._create_unverified_context())
                except OSError as e2:
                    last_err = e2
            else:
                last_err = e
            if raw is None and attempt < retries - 1:
                print(f"[API] 请求异常: {last_err},1s 后重试")
                time.sleep(1)
                continue
        else:
            break
    if raw is None:
        raise ApiError(f"网络请求失败: {type(last_err).__name__}: {last_err}")
    print(f"[API] 收到 {len(raw)} 字节,耗时 {time.time() - t0:.1f}s")
    try:
        return json.loads(raw.decode("utf-8"))
    except ValueError:
        raise ApiError(f"响应不是有效 JSON: {raw[:80]}")

# 提取
def _extract_comic(item):
    if isinstance(item, dict):
        comic = item.get("comic")
        if isinstance(comic, dict):
            return comic
        return item
    return item if isinstance(item, dict) else {}

# 获取作者名
def _author_name(comic):
    authors = comic.get("author")
    if isinstance(authors, list) and authors:
        first = authors[0]
        if isinstance(first, dict):
            return first.get("name", "")
        return str(first)
    return ""


# 登录
def login(username, password, host=None):
    host = host or config.get_api_host()
    salt = 1729
    password_enc = base64.b64encode(f"{password}-{salt}".encode()).decode()
    url = f"https://{host}/api/v3/login"
    body = (f"username={urllib.parse.quote_plus(username)}&"
            f"password={urllib.parse.quote_plus(password_enc)}&salt={salt}")
    headers = _headers()
    headers["Content-Type"] = "application/x-www-form-urlencoded;charset=utf-8"
    res = _do(url, body=body, headers=headers)
    if res.get("code") != 200:
        msg = (res.get("message") or res.get("msg") or res) if isinstance(res, dict) else res
        raise ApiError(f"登录失败: {msg}")
    token = (res.get("results") or {}).get("token")
    if not token:
        raise ApiError("登录失败: 响应中没有 token")
    return token

# 搜索
def search_comics(q, host=None, limit=20, offset=0, q_type=""):
    """按关键词搜索漫画,返回 [{name, path_word, author, cover}]."""
    host = host or config.get_api_host()
    params = {"limit": limit, "offset": offset, "q": q, "q_type": q_type,
                "platform": PLATFORM}
    url = f"https://{host}/api/v3/search/comic?" + urllib.parse.urlencode(params)
    res = _do(url, headers=_headers())
    if res.get("code") != 200:
        raise ApiError(f"搜索失败: {res.get('message') or res}")
    results = res.get("results") or {}
    items = []
    for item in results.get("list") or []:
        comic = _extract_comic(item)
        items.append({"name": comic.get("name", "未知"),
                        "path_word": comic.get("path_word", ""),
                        "author": _author_name(comic),
                        "cover": comic.get("cover", "")})
    return items


# 漫画详情
def _fetch_chapters(path_word, group_path, host):
    eps = []
    offset = 0
    while True:
        url = (f"https://{host}/api/v3/comic/{path_word}/group/{group_path}/chapters"
                f"?limit=100&offset={offset}")
        res = _do(url, headers=_headers())
        if res.get("code") != 200:
            raise ApiError(f"获取章节失败: {res.get('message') or res}")
        results = res.get("results") or {}
        for e in (results.get("list") or []):
            if isinstance(e, dict):
                eps.append({"id": e.get("uuid", ""), "name": e.get("name", "")})
        total = int(results.get("total") or 0)
        offset += 100
        if offset >= total or not results.get("list"):
            break
    return eps


# 已获取的详情缓存
_INFO_CACHE = {}

# 漫画信息
def comic_info(path_word, host=None):
    if path_word in _INFO_CACHE:
        print(f"[API] 命中详情缓存 {path_word}")
        return _INFO_CACHE[path_word]
    host = host or config.get_api_host()
    url = f"https://{host}/api/v3/comic2/{path_word}?platform={PLATFORM}"
    res = _do(url, headers=_headers())
    if res.get("code") != 200:
        raise ApiError(f"获取漫画信息失败: {res.get('message') or res}")
    data = res.get("results")
    if not isinstance(data, dict) or not data.get("comic"):
        raise ApiError(f"获取漫画信息失败: 接口未返回数据({path_word})")
    comic = data.get("comic") or {}
    authors = [a.get("name", "") for a in (comic.get("author") or [])
                if isinstance(a, dict) and a.get("name")]
    tags = [t.get("name", "") for t in (comic.get("theme") or [])
            if isinstance(t, dict) and t.get("name")]
    st = comic.get("status")
    status = st.get("display", "") if isinstance(st, dict) else (st or "")
    groups = []
    for g in (data.get("groups") or {}).values():
        if not isinstance(g, dict) or not g.get("path_word"):
            continue
        chapters = _fetch_chapters(path_word, g["path_word"], host)
        groups.append({"name": g.get("name") or "默认",
                    "path_word": g["path_word"],
                    "chapters": chapters})
    groups.sort(key=lambda g: g["path_word"] != "default")
    result = {"name": comic.get("name", "未知"),
                "cover": comic.get("cover", ""),
                "authors": authors,
                "tags": tags,
                "brief": comic.get("brief", ""),
                "status": status,
                "updated": comic.get("datetime_updated", ""),
                "groups": groups}
    _INFO_CACHE[path_word] = result
    return result


# 章节内容
def chapter(path_word, chapter_uuid, host=None, token=None):
    host = host or config.get_api_host()
    token = token if token is not None else config.get_token()
    url = (f"https://{host}/api/v3/comic/{path_word}/chapter2/{chapter_uuid}"
            f"?platform={PLATFORM}")
    res = _do(url, headers=_headers(token))
    if res.get("code") != 200:
        msg = res.get("message") or res
        if res.get("code") == 210:
            raise ApiError(f"账号被风控(210),请更换账号或稍后再试: {msg}")
        raise ApiError(f"获取章节失败: {msg}")
    return res.get("results") or {}

# 获取章节图片列表
def chapter_pages(path_word, chapter_uuid, host=None, token=None):
    results = chapter(path_word, chapter_uuid, host=host, token=token)
    ch = results.get("chapter") or {}
    contents = ch.get("contents") or []
    words = ch.get("words") or []
    pages = []
    for i, c in enumerate(contents):
        if not isinstance(c, dict):
            continue
        url = (c.get("url") or "").replace(".c800x.", ".c1500x.")
        idx = words[i] if i < len(words) else i
        pages.append((url, idx + 1))
    return pages

# 下载章节图片
def download_page(url, save_path, timeout=8, retries=3):
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout,
                                        context=ssl._create_unverified_context()) as r:
                data = r.read()
            with open(save_path + ".tmp", "wb") as f:
                f.write(data)
            os.replace(save_path + ".tmp", save_path)
            return
        except OSError as e:
            last = e
            if attempt < retries - 1:
                print(f"[API] 图片下载异常: {type(e).__name__}: {e},1s 后重试")
                time.sleep(1)
    raise ApiError(f"图片下载失败: {type(last).__name__}: {last}")


# 收藏
def _auth_headers():
    headers = _headers()
    token = config.get_token()
    if token:
        headers["authorization"] = f"Token {token}"
    return headers

# 收藏列表
def get_favorites(host=None, limit=36, offset=0):
    host = host or config.get_api_host()
    params = {"limit": limit, "offset": offset, "free_type": 1,
                "ordering": "-datetime_updated"}
    url = f"https://{host}/api/v3/member/collect/comics?" + urllib.parse.urlencode(params)
    res = _do(url, headers=_auth_headers())
    if res.get("code") == 401:
        raise ApiError("登录已过期")
    if res.get("code") != 200:
        raise ApiError(f"获取收藏失败: {res.get('message') or res}")
    results = res.get("results") or {}
    items = []
    for item in results.get("list") or []:
        comic = _extract_comic(item)
        items.append({"name": comic.get("name", "未知"),
                    "path_word": comic.get("path_word", ""),
                    "author": _author_name(comic),
                    "cover": comic.get("cover", "")})
    return {"total": int(results.get("total") or len(items)),
            "items": items}

# 查询漫画是否已收藏
def is_favorite(path_word, host=None):
    host = host or config.get_api_host()
    url = f"https://{host}/api/v3/comic2/{path_word}/query"
    res = _do(url, headers=_auth_headers())
    if res.get("code") == 401:
        raise ApiError("登录已过期")
    if res.get("code") != 200:
        raise ApiError(f"查询收藏状态失败: {res.get('message') or res}")
    collect = (res.get("results") or {}).get("collect")
    return collect is not None

# 收藏或取消收藏
def set_favorite(path_word, is_collect, host=None):
    host = host or config.get_api_host()
    url = f"https://{host}/api/v3/comic2/{path_word}?platform={PLATFORM}"
    res = _do(url, headers=_headers())
    if res.get("code") != 200:
        raise ApiError(f"获取漫画信息失败: {res.get('message') or res}")
    comic = (res.get("results") or {}).get("comic") or {}
    comic_id = comic.get("uuid", "")
    if not comic_id:
        raise ApiError("获取漫画 uuid 失败")
    token = config.get_token()
    body = (f"comic_id={urllib.parse.quote_plus(comic_id)}"
            f"&is_collect={1 if is_collect else 0}"
            f"&authorization=Token+{urllib.parse.quote_plus(token)}")
    headers = _auth_headers()
    headers["Content-Type"] = "application/x-www-form-urlencoded;charset=utf-8"
    post_url = f"https://{host}/api/v3/member/collect/comic"
    res = _do(post_url, body=body, headers=headers)
    if res.get("code") == 401:
        raise ApiError("登录已过期")
    if res.get("code") != 200:
        raise ApiError(f"{'收藏' if is_collect else '取消收藏'}失败: {res.get('message') or res}")
    return True
