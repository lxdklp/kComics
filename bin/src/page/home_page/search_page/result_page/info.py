# 漫画详情页
import io
import os
import ssl
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageDraw
import config
from api import copymanga
from export import kindle
from ....layout import px

# 布局比例
MARGIN_X_R = 0.0325
TITLE_Y_R = 0.06
COVER_X_R = 0.0325
COVER_Y_R = 0.14
COVER_W_R = 0.2
INFO_X_R = 0.26
LINE_R = 0.036
BRIEF_Y_R = 0.44
BRIEF_LINE_R = 0.033
TAB_Y_R = 0.56               # 分组选项卡顶边
TAB_H_R = 0.045              # 选项卡高度
TAB_GAP_R = 0.012            # 选项卡间距
CHAP_Y0_R = 0.615            # 有选项卡时章节列表起点
CHAP_Y0_NTAB_R = 0.575       # 无选项卡时保持原布局
CHAP_BOTTOM_R = 0.875
CHAP_GAP_R = 0.005
BTN_W_R, BTN_H_R = 0.155, 0.06
BTN_GAP_R = 0.012
BTN_Y_R = 0.90
POPUP_W_R, POPUP_H_R = 0.568, 0.2
POPUP_LINE_R = 0.0316
DL_CARD_H_R = 0.24           # 下载进度卡片高
DL_LABEL_W_R = 0.22          # 进度条左侧标签区宽
DL_BAR_H_R = 0.018           # 进度条高
DL_ROW1_R = 0.095            # 第一条进度条基线(卡片内)
DL_ROW_GAP_R = 0.06          # 两条进度条基线间距
CHAP_PER_PAGE = 6        # 有选项卡时每页章节数
CHAP_PER_PAGE_NTAB = 8   # 无选项卡时保持原每页数
DL_REFRESH_SEC = 0.3      # 下载时进度刷新节流

IMG_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
IMG_TIMEOUT = 6

STATE = {"item": {}, "info": None, "error": None, "page": 0, "popup": None,
        "group": 0, "selected": set(), "dl": None, "exp": None,
        "from_page": "result", "is_fav": False}

_DL_LOCK = threading.Lock()
_active = lambda: True
_last_show = [0.0]

# —————— 活动指示器(三点动画)与心跳刷屏 ——————
ANIM_SIZE = 8              # 动画方块边长
ANIM_GAP = 6               # 方块间距
_ANIM_TICK = [0]           # 每次渲染 +1,驱动三点动画相位
_HEART_SCREEN = [None]     # 心跳刷屏所需的 screen/fonts 引用(下载启动时登记)
_HEART_FONTS = [None]
_HEARTBEAT = [False]       # 心跳线程只启动一次

def set_active_check(fn):
    global _active
    _active = fn

# 安全化名称
def _safe_name(name):
    for ch in '\\/:*?"<>|':
        name = name.replace(ch, "_")
    return name.strip() or "未知"

# 获取扩展名
def _ext_for(url):
    path = (url or "").split("?")[0].lower().rstrip("/")
    for ext in (".webp", ".jpg", ".jpeg", ".png", ".gif"):
        if path.endswith(ext):
            return ext
    return ".webp"

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

def _wrap_text(draw, text, font, max_w):
    lines = []
    for para in text.split("\n"):
        cur = ""
        for ch in para:
            if draw.textlength(cur + ch, font=font) <= max_w:
                cur += ch
            else:
                if cur:
                    lines.append(cur)
                cur = ch
        if cur:
            lines.append(cur)
    return lines or [text]

# 加载封面
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

# 处理封面
def _fit_cover(img, w, h):
    iw, ih = img.size
    scale = max(w / iw, h / ih)
    nw, nh = int(iw * scale), int(ih * scale)
    img = img.resize((nw, nh), Image.Resampling.LANCZOS)
    x, y = (nw - w) // 2, (nh - h) // 2
    return img.crop((x, y, x + w, y + h))

#获取封面
def _get_cover(info):
    if not info.get("cover"):
        return None
    key = STATE["item"].get("path_word") or info.get("cover")
    imgs = STATE.setdefault("_imgs", {})
    if key in imgs:
        return imgs[key]
    cover = _load_cover(info.get("cover"))
    if cover is not None:
        imgs[key] = cover
    return cover

#分组
def _groups():
    return (STATE["info"] or {}).get("groups") or []

def _tabs():
    return len(_groups()) > 1

def _group_idx():
    idx = STATE["group"]
    return idx if idx < len(_groups()) else 0

def _per_page():
    return CHAP_PER_PAGE if _tabs() else CHAP_PER_PAGE_NTAB

def _chapters():
    groups = _groups()
    if not groups:
        return []
    return groups[_group_idx()].get("chapters") or []

def _pages():
    n = len(_chapters())
    return (n + _per_page() - 1) // _per_page() if n else 1

# 底部按钮
def _bottom_buttons():
    btns = [("上页", "up"), ("返回", "back")]
    if config.get_token():
        btns.append(("取消收藏" if STATE.get("is_fav") else "收藏", "fav"))
    btns.append(("下载", "dl"))
    btns.append(("下页", "down"))
    return btns

# 页面几何
def _grid(w, h):
    mx = px(w, MARGIN_X_R)
    cw = px(w, COVER_W_R)
    cover_h = int(cw * 4 / 3)
    cover = (mx, px(h, COVER_Y_R), cw, cover_h)
    cy0 = px(h, CHAP_Y0_R) if _tabs() else px(h, CHAP_Y0_NTAB_R)
    cy_bottom = px(h, CHAP_BOTTOM_R)
    gap = px(h, CHAP_GAP_R)
    row_h = (cy_bottom - cy0 - (_per_page() - 1) * gap) // _per_page()
    return mx, cover, cy0, row_h, gap

# 下载进度卡片
def _draw_dl_card(draw, w, h, fonts):
    dl = STATE["dl"]
    box_w, box_h = px(w, POPUP_W_R), px(h, DL_CARD_H_R)
    bx, by = (w - box_w) // 2, (h - box_h) // 2
    draw.rounded_rectangle([bx, by, bx + box_w, by + box_h], radius=20,
                            outline=0, width=3, fill=255)
    title = _fit(draw, f"正在下载:{dl['cur_name'] or '…'}", fonts[28],
                 box_w - 2 * px(w, 0.02))
    draw.text(_center(draw, title, fonts[28], bx + box_w // 2, by + px(h, 0.035)),
                title, fill=0, font=fonts[28])
    _draw_anim(draw, bx + box_w - px(w, 0.02), by + px(h, 0.035) + 14,
                _ANIM_TICK[0])
    label_w = px(w, DL_LABEL_W_R)
    bar_h = px(h, DL_BAR_H_R)
    bar_x = bx + px(w, 0.02) + label_w + px(w, 0.015)
    bar_x2 = bx + box_w - px(w, 0.02)
    for i, (tag, done, total) in enumerate((
            ("章节", dl["done"], dl["total"]),
            ("页", dl["page_done"], dl["page_total"]))):
        if tag == "页" and total == 0 and dl["running"]:
            text = "页 获取中…"
        else:
            text = _fit(draw, f"{tag} {done}/{total}", fonts[28], label_w)
        ty = by + px(h, DL_ROW1_R + i * DL_ROW_GAP_R)
        draw.text((bx + px(w, 0.02), ty), text, fill=0, font=fonts[28])
        bar_y = ty + (28 - bar_h) // 2
        draw.rounded_rectangle([bar_x, bar_y, bar_x2, bar_y + bar_h],
                                radius=3, outline=0, width=1)
        if total > 0:
            fw = max(bar_h // 2, int((bar_x2 - bar_x) * done / total))
            draw.rounded_rectangle([bar_x, bar_y, bar_x + fw, bar_y + bar_h],
                                    radius=3, fill=0)

# 导出进度弹窗
def _draw_exp_card(draw, w, h, fonts):
    exp = STATE["exp"]
    box_w, box_h = px(w, POPUP_W_R), px(h, DL_CARD_H_R)
    bx, by = (w - box_w) // 2, (h - box_h) // 2
    draw.rounded_rectangle([bx, by, bx + box_w, by + box_h], radius=20,
                            outline=0, width=3, fill=255)
    stage = exp.get("stage")
    moving = stage == "move"
    title = "正在导出MOBI" if stage == "mobi" else "正在处理图片"
    draw.text(_center(draw, title, fonts[28], bx + box_w // 2,
                        by + px(h, 0.035)), title, fill=0, font=fonts[28])
    _draw_anim(draw, bx + box_w - px(w, 0.02), by + px(h, 0.035) + 14,
                _ANIM_TICK[0])
    label_w = px(w, DL_LABEL_W_R)
    bar_h = px(h, DL_BAR_H_R)
    bar_x = bx + px(w, 0.02) + label_w + px(w, 0.015)
    bar_x2 = bx + box_w - px(w, 0.02)
    if stage == "mobi":
        prefix = "本"
    elif moving:
        prefix = "文件"
    else:
        prefix = "页"
    text = _fit(draw, f"{prefix} {exp['done']}/{exp['total']}", fonts[28], label_w)
    ty = by + px(h, DL_ROW1_R)
    draw.text((bx + px(w, 0.02), ty), text, fill=0, font=fonts[28])
    bar_y = ty + (28 - bar_h) // 2
    draw.rounded_rectangle([bar_x, bar_y, bar_x2, bar_y + bar_h],
                        radius=3, outline=0, width=1)
    if exp["total"] > 0:
        fw = max(bar_h // 2, int((bar_x2 - bar_x) * exp["done"] / exp["total"]))
        draw.rounded_rectangle([bar_x, bar_y, bar_x + fw, bar_y + bar_h],
                                radius=3, fill=0)
    msg = _fit(draw, exp.get("msg") or "", fonts[28], box_w - 2 * px(w, 0.02))
    draw.text(_center(draw, msg, fonts[28], bx + box_w // 2,
                        by + px(h, DL_ROW1_R + DL_ROW_GAP_R)),
                msg, fill=0, font=fonts[28])

# 覆盖确认弹窗
def _draw_ask_popup(draw, w, h, fonts):
    ask = STATE["exp"]["ask"]
    box_w, box_h = px(w, POPUP_W_R), px(h, POPUP_H_R)
    bx, by = (w - box_w) // 2, (h - box_h) // 2
    draw.rounded_rectangle([bx, by, bx + box_w, by + box_h], radius=20,
                            outline=0, width=3, fill=255)
    lines = ask.get("text") or ["已存在,覆盖?"]
    yy = by + (box_h - len(lines) * px(h, POPUP_LINE_R)) // 2 - px(h, 0.02)
    for line in lines:
        draw.text(_center(draw, line, fonts[28], bx + box_w // 2, yy),
                    line, fill=0, font=fonts[28])
        yy += px(h, POPUP_LINE_R)
    bw, bh = px(w, 0.13), px(h, 0.05)
    gap = px(w, 0.06)
    total = 2 * bw + gap
    bx0 = bx + (box_w - total) // 2
    by0 = by + box_h - bh - px(w, 0.02)
    buttons = []
    for label, ans in (("覆盖", True), ("跳过", False)):
        draw.rounded_rectangle([bx0, by0, bx0 + bw, by0 + bh],
                                radius=10, outline=0, width=2)
        draw.text(_center(draw, label, fonts[28], bx0 + bw // 2, by0 + bh // 2),
                    label, fill=0, font=fonts[28])
        buttons.append((label, ans, (bx0, by0, bw, bh)))
        bx0 += bw + gap
    ask["buttons"] = buttons

# 渲染
def render(screen, fonts):
    w, h = screen.output.resolution
    img = Image.new("L", (w, h), 255)
    draw = ImageDraw.Draw(img)
    info = STATE["info"]
    # 加载/错误提示
    if info is None:
        msg = STATE["error"] or "加载中…"
        if isinstance(msg, str):
            msg = [msg]
        for i, line in enumerate(msg):
            draw.text(_center(draw, line, fonts[36], w // 2, h // 2 + i * px(h, POPUP_LINE_R)),
                        line, fill=0, font=fonts[36])
    else:
        mx, cover, cy0, row_h, gap = _grid(w, h)
        # 标题
        title = _fit(draw, info.get("name", "未知"), fonts[36], w - 2 * mx)
        draw.text(_center(draw, title, fonts[36], w // 2, px(h, TITLE_Y_R)),
                    title, fill=0, font=fonts[36])
        # 封面
        cx, cy, cw, cover_h = cover
        draw.rounded_rectangle([cx, cy, cx + cw - 1, cy + cover_h - 1],
                                radius=12, outline=0, width=2)
        cover_img = _get_cover(info)
        if cover_img is not None:
            cropped = _fit_cover(cover_img, cw - 4, cover_h - 4)
            img.paste(cropped, (cx + 2, cy + 2))
        # 右侧信息
        ix = px(w, INFO_X_R)
        iw = w - ix - mx
        line_h = px(h, LINE_R)
        iy = cy
        name_font = fonts[36]
        for label, value in (("作者", ",".join(info.get("authors") or ["未知"])),
                            ("状态", info.get("status") or "未知"),
                            ("更新", info.get("updated") or "未知"),
                            ("标签", ",".join(info.get("tags") or ["无"]))):
            for line in _wrap_text(draw, f"{label}:{value}", name_font, iw):
                draw.text((ix, iy), line, fill=0, font=name_font)
                iy += line_h
        # 简介
        brief = (info.get("brief") or "").strip()
        if brief:
            brief_lines = _wrap_text(draw, brief, fonts[28], w - 2 * mx)
            by = px(h, BRIEF_Y_R)
            for i, bl in enumerate(brief_lines[:3 if _tabs() else 4]):
                draw.text((mx, by + i * px(h, BRIEF_LINE_R)), bl, fill=64, font=fonts[28])
        # 分组选项卡
        groups = _groups()
        if len(groups) > 1:
            n = len(groups)
            tgap = px(w, TAB_GAP_R)
            tw = (w - 2 * mx - (n - 1) * tgap) // n
            ty = px(h, TAB_Y_R)
            th = px(h, TAB_H_R)
            cur = _group_idx()
            for i, g in enumerate(groups):
                tx = mx + i * (tw + tgap)
                name = _fit(draw, g.get("name") or "默认", fonts[28], tw - 8)
                if i == cur:
                    draw.rounded_rectangle([tx, ty, tx + tw - 1, ty + th - 1],
                                            radius=8, fill=0, outline=0)
                    draw.text(_center(draw, name, fonts[28], tx + tw // 2, ty + th // 2),
                                name, fill=255, font=fonts[28])
                else:
                    draw.rounded_rectangle([tx, ty, tx + tw - 1, ty + th - 1],
                                            radius=8, outline=0, width=1)
                    draw.text(_center(draw, name, fonts[28], tx + tw // 2, ty + th // 2),
                                name, fill=0, font=fonts[28])
        # 章节列表
        chapters = _chapters()
        start = STATE["page"] * _per_page()
        chap_font = fonts[28]
        for i in range(_per_page()):
            idx = start + i
            if idx >= len(chapters):
                break
            ch = chapters[idx]
            ry = cy0 + i * (row_h + gap)
            if ch["id"] in STATE["selected"]:
                draw.rounded_rectangle([mx, ry, w - mx, ry + row_h - 1],
                                        radius=10, fill=0, outline=0)
                fill = 255
            else:
                draw.rounded_rectangle([mx, ry, w - mx, ry + row_h - 1],
                                        radius=10, outline=0, width=1)
                fill = 0
            label = _fit(draw, f"{idx + 1}. {ch['name']}", chap_font,
                         w - 2 * mx - px(w, 0.02))
            draw.text((mx + px(w, 0.02), ry + (row_h - 28) // 2),
                        label, fill=fill, font=chap_font)
    # 底部按钮
    bw, bh = px(w, BTN_W_R), px(h, BTN_H_R)
    by = px(h, BTN_Y_R)
    btns = _bottom_buttons()
    total = len(btns) * bw + (len(btns) - 1) * px(w, BTN_GAP_R)
    bx = (w - total) // 2
    pages = _pages()
    for label, action in btns:
        enabled = not ((action == "up" and STATE["page"] == 0)
                        or (action == "down" and STATE["page"] >= pages - 1)
                        or (action == "dl" and (STATE["dl"] or not STATE["selected"])))
        if action == "dl" and STATE["dl"]:
            label = "下载中"
        draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=12, outline=0, width=2)
        draw.text(_center(draw, label, fonts[36], bx + bw // 2, by + bh // 2),
                    label, fill=0 if enabled else 160, font=fonts[36])
        bx += bw + px(w, BTN_GAP_R)
    page_text = f"{STATE['page'] + 1}/{pages}页"
    draw.text(_center(draw, page_text, fonts[28], w // 2, by + bh + px(h, 0.03)),
                page_text, fill=128, font=fonts[28])
    if STATE["dl"]:
        _draw_dl_card(draw, w, h, fonts)
    if STATE["exp"]:
        if STATE["exp"].get("ask"):
            _draw_ask_popup(draw, w, h, fonts)
        else:
            _draw_exp_card(draw, w, h, fonts)
    if STATE["popup"]:
        box_w, box_h = px(w, POPUP_W_R), px(h, POPUP_H_R)
        cx2, cy2 = (w - box_w) // 2, (h - box_h) // 2
        draw.rounded_rectangle([cx2, cy2, cx2 + box_w, cy2 + box_h], radius=20,
                                outline=0, width=3, fill=255)
        yy = cy2 + (box_h - len(STATE["popup"]) * px(h, POPUP_LINE_R)) // 2
        for line in STATE["popup"]:
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
    # 覆盖确认弹窗
    exp = STATE["exp"]
    if exp and exp.get("ask"):
        ask = exp["ask"]
        for _label, ans, rect in ask.get("buttons") or []:
            if _hit(rect, x, y):
                ask["answer"] = ans
                ask["ev"].set()
                exp["ask"] = None
                _show(screen, fonts)
                return None
        return None
    if STATE["dl"] or (exp and exp.get("running")):
        bw, bh = px(w, BTN_W_R), px(h, BTN_H_R)
        by = px(h, BTN_Y_R)
        total = 4 * bw + 3 * px(w, BTN_GAP_R)
        bx = (w - total) // 2
        for label, action in (("上页", "up"), ("返回", "back"), ("下载", "dl"), ("下页", "down")):
            if action == "back" and _hit((bx, by, bw, bh), x, y):
                return "result"
            bx += bw + px(w, BTN_GAP_R)
        return None
    if STATE["popup"]:
        STATE["popup"] = None
        _show(screen, fonts)
        return None
    # 点击选项卡
    if STATE["info"]:
        mx, cover, cy0, row_h, gap = _grid(w, h)
        groups = _groups()
        if len(groups) > 1:
            n = len(groups)
            tgap = px(w, TAB_GAP_R)
            tw = (w - 2 * mx - (n - 1) * tgap) // n
            ty = px(h, TAB_Y_R)
            th = px(h, TAB_H_R)
            cur = _group_idx()
            for i in range(n):
                tx = mx + i * (tw + tgap)
                if i != cur and _hit((tx, ty, tw, th), x, y):
                    STATE["group"] = i
                    STATE["page"] = 0
                    _show(screen, fonts)
                    return None
    # 点击章节行
    if STATE["info"]:
        mx, cover, cy0, row_h, gap = _grid(w, h)
        start = STATE["page"] * _per_page()
        chapters = _chapters()
        for i in range(_per_page()):
            idx = start + i
            if idx >= len(chapters):
                break
            ry = cy0 + i * (row_h + gap)
            if _hit((mx, ry, w - 2 * mx, row_h), x, y):
                ch = chapters[idx]
                if ch["id"] in STATE["selected"]:
                    STATE["selected"].discard(ch["id"])
                else:
                    STATE["selected"].add(ch["id"])
                _show(screen, fonts)
                return None
    # 底部按钮
    bw, bh = px(w, BTN_W_R), px(h, BTN_H_R)
    by = px(h, BTN_Y_R)
    btns = _bottom_buttons()
    total = len(btns) * bw + (len(btns) - 1) * px(w, BTN_GAP_R)
    bx = (w - total) // 2
    pages = _pages()
    for label, action in btns:
        if _hit((bx, by, bw, bh), x, y):
            if action == "back":
                if STATE.get("from_page") == "favorites":
                    from ...favorites import load_first as _fav_load
                    _fav_load(screen, fonts)
                return STATE.get("from_page") or "result"
            if action == "fav":
                _toggle_fav(screen, fonts)
                return None
            if action == "dl":
                if STATE["dl"] or not STATE["selected"]:
                    return None
                _start_download(screen, fonts)
                return None
            if action == "up" and STATE["page"] > 0:
                STATE["page"] -= 1
            if action == "down" and STATE["page"] < pages - 1:
                STATE["page"] += 1
            _show(screen, fonts)
            return None
        bx += bw + px(w, BTN_GAP_R)
    return None

# 收藏/取消收藏
def _toggle_fav(screen, fonts):
    path_word = (STATE.get("item") or {}).get("path_word", "")
    if not path_word:
        return
    new_val = not STATE.get("is_fav")
    try:
        copymanga.set_favorite(path_word, new_val)
    except Exception as e:
        print(f"[详情] 收藏操作失败:{type(e).__name__}: {e}")
        STATE["popup"] = [("收藏" if new_val else "取消收藏") + "失败:"] + _wrap(str(e))
    else:
        STATE["is_fav"] = new_val
        print(f"[详情] 已{'收藏' if new_val else '取消收藏'} {path_word}")
    _show(screen, fonts)

# 下载
def _start_download(screen, fonts):
    _HEART_SCREEN[0] = screen
    _HEART_FONTS[0] = fonts
    _ensure_heartbeat()
    STATE["dl"] = {"running": True, "cur_name": "", "done": 0, "total": 0,
                    "page_done": 0, "page_total": 0}
    _show(screen, fonts)
    threading.Thread(target=_run_download, args=(screen, fonts), daemon=True).start()

# 下载进度刷新
def _maybe_show(screen, fonts):
    if not _active():
        return
    now = time.time()
    if now - _last_show[0] >= DL_REFRESH_SEC:
        _last_show[0] = now
        _show(screen, fonts)

# 下载线程
def _run_download(screen, fonts):
    info = STATE["info"] or {}
    item = STATE["item"] or {}
    comic_dir = _safe_name(info.get("name") or "未知")
    selected = [ch for g in (info.get("groups") or [])
                for ch in (g.get("chapters") or [])
                if ch.get("id") in STATE["selected"]]
    dl = STATE["dl"]
    dl["total"] = len(selected)
    dl["done"] = 0
    dl["page_done"] = 0
    dl["page_total"] = 0
    if not selected or not _active():
        STATE["dl"] = None
        return
    root = os.path.join(config.get_downloads_dir(), comic_dir)
    concurrency = config.get_download_concurrency()
    path_word = item.get("path_word")
    lock = threading.Lock()
    failed = [0]
    remaining = {}
    def _work(ch):
        if not _active():
            return
        with lock:
            dl["cur_name"] = ch.get("name", "")
        chap_dir = os.path.join(root, _safe_name(ch.get("name") or "未知"))
        try:
            pages = copymanga.chapter_pages(path_word, ch["id"])
        except Exception as e:
            print(f"[下载] 章节失败 {ch.get('name')}:{type(e).__name__}: {e}")
            with lock:
                failed[0] += 1
            return
        try:
            os.makedirs(chap_dir, exist_ok=True)
        except OSError as e:
            print(f"[下载] 创建目录失败 {chap_dir}:{e}")
            with lock:
                failed[0] += 1
            return
        if not pages:
            with lock:
                dl["done"] += 1
            _maybe_show(screen, fonts)
            return
        with lock:
            dl["page_total"] += len(pages)
            remaining[ch["id"]] = len(pages)
        try:
            for url, page in pages:
                pool.submit(_dl_page, ch["id"], chap_dir, url, page)
        except Exception as e:
            print(f"[下载] 提交页任务失败 {ch.get('name')}:{type(e).__name__}: {e}")
            with lock:
                failed[0] += 1
    def _dl_page(chid, chap_dir, url, page):
        if not _active():
            return
        path = os.path.join(chap_dir, f"{page:03d}{_ext_for(url)}")
        try:
            copymanga.download_page(url, path)
        except Exception as e:
            print(f"[下载] 图片失败 第{page}页:{type(e).__name__}: {e}")
            with lock:
                failed[0] += 1
        with lock:
            dl["page_done"] += 1
            remaining[chid] -= 1
            if remaining[chid] <= 0:
                dl["done"] += 1
        _maybe_show(screen, fonts)

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        work_futs = [pool.submit(_work, ch) for ch in selected]
        for fut in work_futs:
            fut.result()
    if not _active():
        STATE["dl"] = None
        return
    STATE["selected"].clear()
    STATE["dl"] = None
    STATE["popup"] = ["下载完成" if not failed[0]
                        else f"下载完成({failed[0]} 项失败)"]
    print(f"[下载] 完成:成功 {dl['done']}/{dl['total']} 章,{failed[0]} 项失败")
    _show(screen, fonts)
    docs = config.get_kindle_documents_dir()
    if docs:
        try:
            os.makedirs(docs, exist_ok=True)
        except OSError as e:
            print(f"[导出] 创建书库目录失败:{type(e).__name__}: {e}")
            STATE["popup"] = ["下载完成", "创建Kindle书库目录失败,已跳过导出"]
            _show(screen, fonts)
            return
        STATE["popup"] = None
        STATE["exp"] = {"running": True, "msg": "准备中…", "done": 0, "total": 0,
                        "cur_book": "", "stage": "build", "ask": None}
        _show(screen, fonts)
        threading.Thread(target=_run_export, args=(screen, fonts, comic_dir),
                        daemon=True).start()
    else:
        STATE["popup"] = ["下载完成", "未配置Kindle书库目录,已跳过导出"]
        _show(screen, fonts)

# 导出进度回调
def _exp_progress(screen, fonts, done, total, bname):
    exp = STATE["exp"]
    if exp:
        exp["stage"] = "build"
        if bname and bname != exp["cur_book"]:
            exp["cur_book"] = bname
        exp["done"], exp["total"], exp["msg"] = done, total, bname
    _maybe_show(screen, fonts)

# 导出阶段回调
def _exp_stage(screen, fonts, stage, done, total, name):
    exp = STATE["exp"]
    if exp:
        exp["stage"] = stage
        exp["done"], exp["total"], exp["msg"] = done, total, name or exp.get("msg", "")
    _maybe_show(screen, fonts)

# 覆盖确认
def _ask_overwrite(screen, fonts, filename):
    exp = STATE["exp"]
    ev = threading.Event()
    ask = {"ev": ev, "answer": False,
            "text": [f"{filename}", "已存在,覆盖?"], "buttons": []}
    exp["ask"] = ask
    _show(screen, fonts)
    ev.wait(30)
    if exp["ask"] is ask:
        exp["ask"] = None
    return ask["answer"]

# 导出线程
def _run_export(screen, fonts, comic_title):
    resolution = None
    try:
        w, h = screen.output.resolution
        resolution = f'{w}x{h}'
    except Exception:
        pass
    # 灰度屏(EPDC bpp=1/8)才灰度化导出;彩色屏幕机型(Scribe 2025/Colorsoft)保持彩色
    grayscale = config.get_export_grayscale()
    try:
        disp = screen.output.display
        if disp is not None and getattr(disp, "bpp", 8) not in (1, 8):
            grayscale = False
    except Exception:
        pass
    try:
        ok, msg = kindle.export_comic(
            comic_title,
            merged=config.get_export_merged(),
            chapters_per_book=config.get_export_chapters_per_book(),
            rtl=config.get_export_rtl(),
            docs_dir=config.get_kindle_documents_dir(),
            resolution=resolution,
            grayscale=grayscale,
            progress=lambda d, t, n: _exp_progress(screen, fonts, d, t, n),
            stage_callback=lambda s, d, t, n: _exp_stage(screen, fonts, s, d, t, n),
            ask_overwrite=lambda fn: _ask_overwrite(screen, fonts, fn))
    except Exception as e:
        print(f"[导出] 失败:{type(e).__name__}: {e}")
        STATE["exp"] = None
        STATE["popup"] = [f"导出失败:{type(e).__name__}"]
    else:
        STATE["exp"] = None
        STATE["popup"] = [msg]
    print(f"[导出] {msg}") # type: ignore
    if _active():
        _show(screen, fonts)

# 上屏
def _show(screen, fonts):
    _ANIM_TICK[0] += 1   # 每次实际渲染都前进一帧动画
    with _DL_LOCK:
        try:
            screen.output.show(render(screen, fonts),
                                is_flashing=bool(STATE["popup"]) and not STATE["dl"])
        except OSError as e:
            print(f"[输出] 刷新失败:{e}")

# —————— 活动指示器与心跳 ——————

# 动画盒:弹窗右上角区域 (x, y, w, h),绘制与局部刷新共用同一几何
def _anim_box(w, h):
    box_w = px(w, POPUP_W_R)
    bx = (w - box_w) // 2
    x_right = bx + box_w - px(w, 0.02)
    y_center = (h - px(h, DL_CARD_H_R)) // 2 + px(h, 0.035) + 14
    total = 3 * ANIM_SIZE + 2 * ANIM_GAP
    return (x_right - total - 4, y_center - ANIM_SIZE // 2 - 4,
            total + 8, ANIM_SIZE + 8)

# 绘制三点指示器:第 phase%3 个实心,其余空心
def _draw_anim(draw, x_right, y_center, phase):
    for i in range(3):
        x0 = x_right - (2 - i) * (ANIM_SIZE + ANIM_GAP) - ANIM_SIZE
        y0 = y_center - ANIM_SIZE // 2
        if i == phase % 3:
            draw.rectangle([x0, y0, x0 + ANIM_SIZE, y0 + ANIM_SIZE], fill=0)
        else:
            draw.rectangle([x0, y0, x0 + ANIM_SIZE, y0 + ANIM_SIZE],
                            outline=0, width=1)

# 心跳线程(常驻,只启动一次):弹窗活跃期间每 ~1.2s 局部刷新动画盒,
# 让用户在处理图片/构建 MOBI 等静默阶段也能看到程序在运行(不整屏刷,无全屏闪烁)
# 诊断日志:[心跳] 执行 N 次,刷新被拒 M 次 —— 用于区分 线程饿死/ioctl被拒/EPDC吞更新
def _ensure_heartbeat():
    if _HEARTBEAT[0]:
        return
    _HEARTBEAT[0] = True

    diag = {"n": 0, "last_log": 0, "rejected": 0}

    def _beat():
        while True:
            time.sleep(DL_REFRESH_SEC * 4)
            try:
                screen = _HEART_SCREEN[0]
                if screen is None or not _active():
                    continue
                if not (STATE.get("dl") or STATE.get("exp")):
                    continue
                _ANIM_TICK[0] += 1
                with _DL_LOCK:
                    from screen.output import WAVEFORM  # 延迟导入:避免把 fcntl 拉进测试环境
                    w, h = screen.output.resolution
                    img = render(screen, _HEART_FONTS[0])
                    marker = screen.output.show(img, is_flashing=False,
                                                waveform_mode=WAVEFORM.GC16,
                                                region=_anim_box(w, h))
                diag["n"] += 1
                if marker is None:
                    diag["rejected"] += 1
                # 每 30 次(约36s)打一条;一旦出现被拒立即打一条
                if diag["n"] - diag["last_log"] >= 30 or \
                        (marker is None and diag["n"] - diag["last_log"] >= 5):
                    diag["last_log"] = diag["n"]
                    print(f"[心跳] 执行 {diag['n']} 次,刷新被拒 {diag['rejected']} 次"
                          f"(marker={marker})")
            except Exception as e:
                print(f"[输出] 心跳刷新异常:{type(e).__name__}: {e}")

    threading.Thread(target=_beat, daemon=True).start()
