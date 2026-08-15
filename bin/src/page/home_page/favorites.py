# 收藏页
import io
import ssl
import threading
import urllib.request
from PIL import Image, ImageDraw
from api import copymanga
from ..layout import px

TITLE = "我的收藏"
COLS, ROWS = 3, 2
PER_PAGE = COLS * ROWS
LOAD_LIMIT = 36

STATE = {"list": [], "page": 0, "total": 0, "offset": 0,
        "loading": False, "popup": None}

# 注册页面切换回调
_NAVIGATE = None
def set_navigate(fn):
    """注册页面切换回调(kcomics 调用),供详情加载完成后的后台线程使用."""
    global _NAVIGATE
    _NAVIGATE = fn

# 布局比例
TITLE_Y_R = 0.06
GRID_Y0_R = 0.14
MARGIN_X_R = 0.0325
GAP_X_R = 0.02
GAP_Y_R = 0.018
NAME_H_R = 0.035
BTN_W_R, BTN_H_R = 0.24, 0.06
BTN_Y_R = 0.90
POPUP_W_R, POPUP_H_R = 0.568, 0.2
POPUP_LINE_R = 0.0316

IMG_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
IMG_TIMEOUT = 6

def _center(draw, text, font, cx, cy):
    bbox = draw.textbbox((0, 0), text, font=font)
    return (cx - (bbox[2] - bbox[0]) // 2 - bbox[0],
            cy - (bbox[3] - bbox[1]) // 2 - bbox[1])

def _wrap(text, n=16):
    return [text[i:i + n] for i in range(0, len(text), n)] or [text]

def _fit(draw, text, font, max_w):
    if draw.textlength(text, font=font) <= max_w:
        return text
    while text and draw.textlength(text + "…", font=font) > max_w:
        text = text[:-1]
    return text + "…"

# 下载封面图
def _load_cover(url):
    if not url:
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": IMG_UA})
        with urllib.request.urlopen(req, timeout=IMG_TIMEOUT,
                                    context=ssl._create_unverified_context()) as r:
            data = r.read()
        img = Image.open(io.BytesIO(data))
        img.load()
        return img.convert("L")
    except Exception as e:
        print(f"[封面] 下载失败 {url[:60]}:{type(e).__name__}: {e}")
        return None

# 封面图处理
def _fit_cover(img, w, h):
    iw, ih = img.size
    scale = max(w / iw, h / ih)
    nw, nh = int(iw * scale), int(ih * scale)
    img = img.resize((nw, nh), Image.Resampling.LANCZOS)
    x, y = (nw - w) // 2, (nh - h) // 2
    return img.crop((x, y, x + w, y + h))

# 封面图缓存
def _get_cover(item):
    if not item.get("cover"):
        return None
    key = item.get("path_word") or item.get("cover")
    imgs = STATE.setdefault("_imgs", {})
    if key in imgs:
        return imgs[key]
    cover = _load_cover(item.get("cover"))
    if cover is not None:
        imgs[key] = cover
    return cover

# 网格布局计算
def _grid(w, h):
    mx = px(w, MARGIN_X_R)
    gx = px(w, GAP_X_R)
    gy = px(h, GAP_Y_R)
    name_h = px(h, NAME_H_R)
    cw = (w - 2 * mx - (COLS - 1) * gx) // COLS
    cover_h = int(cw * 4 / 3)
    y0 = px(h, GRID_Y0_R)
    return mx, y0, gx, gy, cw, cover_h, name_h

# 计算总页数
def _pages():
    n = STATE.get("total") or len(STATE["list"])
    return (n + PER_PAGE - 1) // PER_PAGE if n else 1

# 追加加载下一批收藏
def _load_more(screen, fonts):
    if STATE["loading"]:
        return
    offset = STATE["offset"]
    if offset > 0 and offset >= STATE["total"]:
        return
    STATE["loading"] = True
    STATE["popup"] = ["加载中…"]
    _show(screen, fonts)
    def _run():
        try:
            data = copymanga.get_favorites(limit=LOAD_LIMIT, offset=offset)
            STATE["list"].extend(data["items"])
            STATE["total"] = data["total"]
            STATE["offset"] = offset + LOAD_LIMIT
        except Exception as e:
            print(f"[收藏] 加载失败:{type(e).__name__}: {e}")
            STATE["popup"] = ["加载收藏失败:"] + _wrap(str(e))
        STATE["loading"] = False
        if STATE["popup"] == ["加载中…"]:
            STATE["popup"] = None
        _show(screen, fonts)
    threading.Thread(target=_run, daemon=True).start()

# 首次加载
def load_first(screen, fonts):
    STATE["list"], STATE["page"], STATE["offset"], STATE["total"] = [], 0, 0, 0
    _load_more(screen, fonts)

# 渲染
def render(screen, fonts):
    w, h = screen.output.resolution
    img = Image.new("L", (w, h), 255)
    draw = ImageDraw.Draw(img)
    draw.text(_center(draw, TITLE, fonts[36], w // 2, int(h * TITLE_Y_R)),
                TITLE, fill=0, font=fonts[36])
    mx, y0, gx, gy, cw, cover_h, name_h = _grid(w, h)
    name_font = fonts[28]
    start = STATE["page"] * PER_PAGE
    for i in range(PER_PAGE):
        idx = start + i
        if idx >= len(STATE["list"]):
            break
        row, col = divmod(i, COLS)
        cx = mx + col * (cw + gx)
        cy = y0 + row * (cover_h + name_h + gy)
        cell_h = cover_h + name_h
        draw.rounded_rectangle([cx, cy, cx + cw - 1, cy + cell_h - 1],
                                radius=14, outline=0, width=2)
        item = STATE["list"][idx]
        cover = _get_cover(item)
        if cover is not None:
            cropped = _fit_cover(cover, cw - 4, cover_h - 4)
            img.paste(cropped, (cx + 2, cy + 2))
        name = _fit(draw, item.get("name", "未知"), name_font, cw - 8)
        ny = cy + cover_h + (name_h - 28) // 2
        draw.text((cx + (cw - draw.textlength(name, font=name_font)) // 2, ny),
                    name, fill=0, font=name_font)
    bw, bh = px(w, BTN_W_R), px(h, BTN_H_R)
    by = px(h, BTN_Y_R)
    total = 3 * bw + 2 * px(w, 0.02)
    bx = (w - total) // 2
    pages = _pages()
    for label, action in (("上页", "up"), ("返回", "back"), ("下页", "down")):
        enabled = not ((action == "up" and STATE["page"] == 0)
                        or (action == "down" and STATE["page"] >= pages - 1))
        draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=12, outline=0, width=2)
        draw.text(_center(draw, label, fonts[36], bx + bw // 2, by + bh // 2),
                    label, fill=0 if enabled else 160, font=fonts[36])
        bx += bw + px(w, 0.02)
    page_text = f"{STATE['page'] + 1}/{pages}页"
    draw.text(_center(draw, page_text, fonts[28], w // 2, by + bh + px(h, 0.03)),
                page_text, fill=128, font=fonts[28])
    if STATE["popup"]:
        lines = STATE["popup"]
        box_w, box_h = px(w, POPUP_W_R), px(h, POPUP_H_R)
        cx2, cy2 = (w - box_w) // 2, (h - box_h) // 2
        draw.rounded_rectangle([cx2, cy2, cx2 + box_w, cy2 + box_h], radius=20,
                                outline=0, width=3, fill=255)
        yy = cy2 + (box_h - len(lines) * px(h, POPUP_LINE_R)) // 2
        for line in lines:
            draw.text(_center(draw, line, fonts[36], cx2 + box_w // 2, yy),
                        line, fill=0, font=fonts[36])
            yy += px(h, POPUP_LINE_R)
    return img

def _hit(rect, x, y):
    rx, ry, rw, rh = rect
    return rx <= x < rx + rw and ry <= y < ry + rh

# 触控处理
def handle(data, screen, fonts):
    if data["gesture"] != "tap":
        return None
    x, y = data["x-pixel"], data["y-pixel"]
    w, h = screen.output.resolution
    if STATE["popup"]:
        if STATE["loading"]:
            return None
        STATE["popup"] = None
        _show(screen, fonts)
        return None
    mx, y0, gx, gy, cw, cover_h, name_h = _grid(w, h)
    cell_h = cover_h + name_h
    start = STATE["page"] * PER_PAGE
    for i in range(PER_PAGE):
        idx = start + i
        if idx >= len(STATE["list"]):
            break
        row, col = divmod(i, COLS)
        cx = mx + col * (cw + gx)
        cy = y0 + row * (cover_h + name_h + gy)
        if _hit((cx, cy, cw, cell_h), x, y):
            item = STATE["list"][idx]
            print(f"[收藏] 点击 {item.get('name')} → 详情页")
            from .search_page.result_page import info  # 延迟导入
            info.STATE.update(item=item, info=None, error=None, page=0, popup=None,
                                group=0, from_page="favorites", is_fav=False)
            STATE["popup"] = ["加载中…"]
            _show(screen, fonts)
            def _run():
                try:
                    data = copymanga.comic_info(item.get("path_word"))
                except Exception as e:
                    print(f"[详情] 获取失败:{type(e).__name__}: {e}")
                    data = None
                    info.STATE["error"] = ["获取详情失败:"] + _wrap(str(e))
                info.STATE["info"] = data
                try:
                    info.STATE["is_fav"] = copymanga.is_favorite(item.get("path_word"))
                except Exception as e:
                    print(f"[详情] 查询收藏状态失败:{type(e).__name__}: {e}")
                STATE["popup"] = None
                if _NAVIGATE is not None:
                    _NAVIGATE("info")
                else:
                    _show(screen, fonts)
            threading.Thread(target=_run, daemon=True).start()
            return None
    # 底部按钮
    bw, bh = px(w, BTN_W_R), px(h, BTN_H_R)
    by = px(h, BTN_Y_R)
    total = 3 * bw + 2 * px(w, 0.02)
    bx = (w - total) // 2
    pages = _pages()
    for label, action in (("上页", "up"), ("返回", "back"), ("下页", "down")):
        if _hit((bx, by, bw, bh), x, y):
            if action == "back":
                return "home"
            if action == "up" and STATE["page"] > 0:
                STATE["page"] -= 1
                _show(screen, fonts)
                return None
            if action == "down" and STATE["page"] < pages - 1:
                STATE["page"] += 1
                need = (STATE["page"] + 1) * PER_PAGE
                if need > len(STATE["list"]) and STATE["offset"] < STATE["total"]:
                    _load_more(screen, fonts)
                else:
                    _show(screen, fonts)
                return None
        bx += bw + px(w, 0.02)
    return None

# 上屏
def _show(screen, fonts):
    try:
        screen.output.show(render(screen, fonts), is_flashing=bool(STATE["popup"]))
    except OSError as e:
        print(f"[输出] 刷新失败:{e}")
