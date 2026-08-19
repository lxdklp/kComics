# 设置页
import os
import shutil
import threading

import config

from PIL import Image, ImageDraw

from ..layout import px
from .. import keyboard

TITLE = "设置"

# 配置项
ITEMS = (
    ("api_url", "拷贝漫画 API 地址", "str"),
    ("download_concurrency", "下载并发数", "num"),
    ("export_merged", "多章节合并", "bool"),
    ("export_chapters_per_book", "单本所含最大章数", "num"),
    ("export_rtl", "向右翻页", "bool"),
    ("check_update", "自动检查更新", "bool"),
)
EXIT_ITEM = ("__exit__", "退出登录", "exit")
CLEAN_ITEM = ("__clean__", "清理缓存", "clean")
SDR_ITEM = ("__sdr__", "清理 kComics 文件夹的多余 sdr", "sdr")
LIB_ITEM = ("__library__", "显示在图书馆", "library")
PER_PAGE = 8
STR_CAPS = ("en", "numsym")
NUM_CAPS = ("num",)

STATE = {"page": 0, "confirm": None, "cleaning": False, "popup": None,
        "dir_size": None, "stat_loading": False, "library_on": None,
        "sdr_orphans": None}

# 布局比例
TITLE_Y_R = 0.09
ITEM_Y0_R = 0.15
ITEM_H_R = 0.075
ITEM_GAP_R = 0.012
BTN_W_R, BTN_H_R = 0.24, 0.06
BTN_GAP_R = 0.02
BTN_Y_R = 0.90
POPUP_W_R, POPUP_H_R = 0.568, 0.2
POPUP_LINE_R = 0.04

# 设置项
def _all_items():
    items = list(ITEMS)
    items.append(CLEAN_ITEM)
    items.append(SDR_ITEM)
    if _install_mode() == "kual":
        items.append(LIB_ITEM)
    if _logged_in():
        items.append(EXIT_ITEM)
    return items

def _pages():
    n = len(_all_items())
    return (n + PER_PAGE - 1) // PER_PAGE if n else 1

def _item_rects(w, h):
    """返回当前页设置项矩形列表 [(idx, rect), ...]."""
    rects = []
    item_h = px(h, ITEM_H_R)
    gap = px(h, ITEM_GAP_R)
    y = px(h, ITEM_Y0_R)
    start = STATE["page"] * PER_PAGE
    for i in range(PER_PAGE):
        idx = start + i
        if idx >= len(_all_items()):
            break
        rects.append((idx, (px(w, 0.05), y, px(w, 0.9), item_h)))
        y += item_h + gap
    return rects

def _bottom_rects(w, h):
    bw, bh = px(w, BTN_W_R), px(h, BTN_H_R)
    by = px(h, BTN_Y_R)
    total = 3 * bw + 2 * px(w, BTN_GAP_R)
    bx = (w - total) // 2
    rects = []
    for _ in range(3):
        rects.append((bx, by, bw, bh))
        bx += bw + px(w, BTN_GAP_R)
    return rects

def _center(draw, text, font, cx, cy):
    bbox = draw.textbbox((0, 0), text, font=font)
    return (cx - (bbox[2] - bbox[0]) // 2 - bbox[0],
            cy - (bbox[3] - bbox[1]) // 2 - bbox[1])

def _hit(rect, x, y):
    rx, ry, rw, rh = rect
    return rx <= x < rx + rw and ry <= y < ry + rh

def _logged_in():
    return bool(config.get_token())

# 统计缓存大小
def _dir_size(path):
    if not os.path.isdir(path):
        return 0
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total

def _cache_dirs():
    return (config.get_downloads_dir(), config.get_export_tmp_dir())

_DOC_EXTS = (".mobi", ".azw3", ".azw", ".epub", ".pdf", ".txt",
            ".prc", ".doc", ".docx", ".html", ".htm")

def _base_name(name):
    low = name.lower()
    for ext in _DOC_EXTS:
        if low.endswith(ext):
            return name[:-len(ext)]
    return name

# sdr清理
def _sdr_orphans():
    base = config.get_kindle_documents_dir()
    if not os.path.isdir(base):
        return []
    names = os.listdir(base)
    stems = {_base_name(n).lower() for n in names
            if not n.lower().endswith(".sdr")}
    orphans = []
    for n in names:
        if not n.lower().endswith(".sdr"):
            continue
        stem = _base_name(n[:-4]).lower()
        if stem not in stems:
            orphans.append(os.path.join(base, n))
    return orphans

# 格式化字节数
def _fmt_size(n):
    if n < 1024:
        return f"{n}B"
    if n < 1024 ** 2:
        return f"{n / 1024:.1f}KB"
    if n < 1024 ** 3:
        return f"{n / 1024 ** 2:.1f}MB"
    return f"{n / 1024 ** 3:.1f}GB"

# 刷新
def refresh_size(screen, fonts):
    if STATE["stat_loading"]:
        return
    STATE["stat_loading"] = True
    STATE["dir_size"] = None
    STATE["library_on"] = None
    _show(screen, fonts)
    def _run():
        try:
            STATE["dir_size"] = sum(_dir_size(p) for p in _cache_dirs())
        except Exception as e:
            print(f"[设置] 统计缓存大小失败:{type(e).__name__}: {e}")
            STATE["dir_size"] = 0
        try:
            STATE["library_on"] = _lib_on() if _install_mode() == "kual" else False
        except Exception as e:
            print(f"[设置] 检测图书馆开关失败:{type(e).__name__}: {e}")
            STATE["library_on"] = False
        try:
            STATE["sdr_orphans"] = len(_sdr_orphans())
        except Exception as e:
            print(f"[设置] 检测多余 sdr 失败:{type(e).__name__}: {e}")
            STATE["sdr_orphans"] = 0
        STATE["stat_loading"] = False
        _show(screen, fonts)
    threading.Thread(target=_run, daemon=True).start()

# 清理缓存
def _clear_dir(path):
    if not os.path.isdir(path):
        return
    for name in os.listdir(path):
        p = os.path.join(path, name)
        try:
            if os.path.isdir(p) and not os.path.islink(p):
                shutil.rmtree(p)
            else:
                os.unlink(p)
        except OSError as e:
            print(f"[设置] 删除失败 {p}:{type(e).__name__}: {e}")

def start_clean(screen, fonts):
    if STATE["cleaning"]:
        return
    STATE["cleaning"] = True
    STATE["confirm"] = None
    STATE["popup"] = None
    _show(screen, fonts)
    def _run():
        freed = 0
        try:
            freed = sum(_dir_size(p) for p in _cache_dirs())
            for p in _cache_dirs():
                _clear_dir(p)
        except Exception as e:
            print(f"[设置] 清理缓存失败:{type(e).__name__}: {e}")
            STATE["popup"] = ["清理失败:"] + _wrap(str(e))
        else:
            print(f"[设置] 清理完成,释放 {freed} 字节")
            STATE["popup"] = [f"清理完成(释放 {_fmt_size(freed)})"]
        STATE["cleaning"] = False
        STATE["dir_size"] = 0
        _show(screen, fonts)
    threading.Thread(target=_run, daemon=True).start()

# 清理 sdr
def start_clean_sdr(screen, fonts):
    if STATE["cleaning"]:
        return
    STATE["cleaning"] = True
    STATE["confirm"] = None
    STATE["popup"] = None
    _show(screen, fonts)
    def _run():
        orphans = _sdr_orphans()
        n_ok, n_fail = 0, 0
        for p in orphans:
            try:
                shutil.rmtree(p)
                n_ok += 1
            except OSError as e:
                print(f"[设置] 删除 sdr 失败 {p}:{type(e).__name__}: {e}")
                n_fail += 1
        print(f"[设置] 已删除 {n_ok} 个多余 sdr(失败 {n_fail})")
        STATE["cleaning"] = False
        STATE["sdr_orphans"] = 0
        if n_fail:
            STATE["popup"] = [f"已删除 {n_ok} 个 sdr({n_fail} 个失败)"]
        elif n_ok:
            STATE["popup"] = [f"已删除 {n_ok} 个多余 sdr"]
        else:
            STATE["popup"] = ["无多余 sdr"]
        _show(screen, fonts)
    threading.Thread(target=_run, daemon=True).start()

def _wrap(text, n=16):
    return [text[i:i + n] for i in range(0, len(text), n)] or [text]

# 显示在图书馆
def _bin_dir():
    """返回 bin 目录(本项目脚本所在目录,settings.py 上溯 4 级)."""
    return os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))

# 安装方式
def _install_mode():
    root = os.path.dirname(_bin_dir())
    if root.startswith("/mnt/us/extensions/"):
        return "kual"
    if root.startswith("/mnt/us/kmc/kpm/packages/"):
        return "kpm"
    return "unknown"

def _lib_paths():
    """返回 (源文件 bin/kual.sh, 目标 documents/kual.sh)."""
    return (os.path.join(_bin_dir(), "kual.sh"),
            os.path.join(config.get_kindle_documents_dir(), "kual.sh"))

# 检查 kual.sh
def _same_file(a, b):
    try:
        if os.path.getsize(a) != os.path.getsize(b):
            return False
        with open(a, "rb") as fa, open(b, "rb") as fb:
            return fa.read() == fb.read()
    except OSError:
        return False

def _lib_on():
    src, dst = _lib_paths()
    return _same_file(src, dst)

def toggle_library(screen, fonts):
    src, dst = _lib_paths()
    on = bool(STATE["library_on"])
    try:
        if on:
            if os.path.exists(dst):
                os.unlink(dst)
            print(f"[设置] 已从图书馆移除 kual.sh({dst})")
        else:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            print(f"[设置] 已部署 kual.sh 到图书馆({dst})")
        STATE["library_on"] = not on
    except Exception as e:
        print(f"[设置] 切换图书馆开关失败:{type(e).__name__}: {e}")
        STATE["popup"] = ["操作失败"] + _wrap(str(e))[:2]
    _show(screen, fonts)

# 渲染
def render(screen, fonts):
    w, h = screen.output.resolution
    img = Image.new("L", (w, h), 255)
    draw = ImageDraw.Draw(img)
    draw.text(_center(draw, TITLE, fonts[96], w // 2, int(h * TITLE_Y_R)),
                TITLE, fill=0, font=fonts[96])
    cfg = config.load()
    items = _all_items()
    # 设置项
    for idx, (rx, ry, rw, rh) in _item_rects(w, h):
        key, label, itype = items[idx]
        draw.rounded_rectangle([rx, ry, rx + rw, ry + rh], radius=12,
                                outline=0, width=2)
        draw.text((rx + px(w, 0.03), ry + (rh - 36) // 2), label,
                    fill=0, font=fonts[36])
        if itype == "exit":
            show = str(cfg.get("username") or "")
        elif itype == "clean":
            if STATE["cleaning"]:
                show = "清理中…"
            elif STATE["dir_size"] is None:
                show = "统计中…"
            else:
                show = f"共 {_fmt_size(STATE['dir_size'] or 0)}"
        elif itype == "library":
            if STATE["library_on"] is None:
                show = "检测中…"
            else:
                show = "开" if STATE["library_on"] else "关"
        elif itype == "sdr":
            if STATE["cleaning"]:
                show = "清理中…"
            elif STATE["sdr_orphans"] is None:
                show = "检测中…"
            else:
                show = f"{STATE['sdr_orphans']} 个" if STATE["sdr_orphans"] else "无"
        elif itype == "bool":
            show = "开" if cfg.get(key) else "关"
        else:
            show = str(cfg.get(key) if cfg.get(key) is not None else "")
        if len(show) > 22:
            show = show[:19] + "..."
        bbox = draw.textbbox((0, 0), show, font=fonts[36])
        draw.text((rx + rw - (bbox[2] - bbox[0]) - px(w, 0.03),
                   ry + (rh - 36) // 2), show, fill=0, font=fonts[36])
    bw, bh = px(w, BTN_W_R), px(h, BTN_H_R)
    by = px(h, BTN_Y_R)
    rects = _bottom_rects(w, h)
    pages = _pages()
    for label, action, rect in zip(
            ("上页", "返回", "下页"), ("up", "back", "down"), rects):
        enabled = not ((action == "up" and STATE["page"] == 0)
                        or (action == "down" and STATE["page"] >= pages - 1))
        rx, ry, rw2, rh2 = rect
        draw.rounded_rectangle([rx, ry, rx + rw2, ry + rh2], radius=12,
                                outline=0, width=2)
        draw.text(_center(draw, label, fonts[36], rx + rw2 // 2, ry + rh2 // 2),
                    label, fill=0 if enabled else 160, font=fonts[36])
    page_text = f"{STATE['page'] + 1}/{pages}页"
    draw.text(_center(draw, page_text, fonts[28], w // 2, by + bh + px(h, 0.03)),
                page_text, fill=128, font=fonts[28])
    # 弹窗
    if STATE["cleaning"]:
        _draw_text_popup(draw, fonts, w, h, ["清理中…"])
    elif STATE["confirm"] == "exit":
        _draw_confirm_popup(draw, fonts, w, h, "确认退出登录?")
    elif STATE["confirm"] == "clean":
        size_txt = "" if STATE["dir_size"] is None \
            else f"(共 {_fmt_size(STATE['dir_size'] or 0)})"
        _draw_confirm_popup(draw, fonts, w, h, "确认清理缓存?",
                            f"将清空 downloads 和 tmp{size_txt}")
    elif STATE["confirm"] == "sdr":
        _draw_confirm_popup(draw, fonts, w, h, "确认清理 kComics 文件夹的多余 sdr?",
                            f"将删除 {STATE['sdr_orphans'] or 0} 个孤儿 sdr 文件夹")
    elif STATE["popup"]:
        _draw_text_popup(draw, fonts, w, h, STATE["popup"])
    return img

# 弹窗布局
def _popup_box(w, h):
    box_w, box_h = px(w, POPUP_W_R), px(h, POPUP_H_R)
    return box_w, box_h, (w - box_w) // 2, (h - box_h) // 2

# 确认弹窗
def _draw_confirm_popup(draw, fonts, w, h, title, subtitle=None):
    box_w, box_h, cx2, cy2 = _popup_box(w, h)
    draw.rounded_rectangle([cx2, cy2, cx2 + box_w, cy2 + box_h], radius=20,
                            outline=0, width=3, fill=255)
    if subtitle:
        draw.text(_center(draw, title, fonts[36], cx2 + box_w // 2, cy2 + box_h * 0.26),
                    title, fill=0, font=fonts[36])
        draw.text(_center(draw, subtitle, fonts[28], cx2 + box_w // 2, cy2 + box_h * 0.46),
                    subtitle, fill=0, font=fonts[28])
    else:
        draw.text(_center(draw, title, fonts[36], cx2 + box_w // 2, cy2 + box_h * 0.35),
                    title, fill=0, font=fonts[36])
    bw2, bh2 = px(w, 0.2), px(h, BTN_H_R)
    gap2 = px(w, 0.08)
    bx2 = cx2 + (box_w - 2 * bw2 - gap2) // 2
    by2 = cy2 + box_h * 0.6
    draw.rounded_rectangle([bx2, by2, bx2 + bw2, by2 + bh2], radius=10,
                            outline=0, width=2)
    draw.text(_center(draw, "确定", fonts[28], bx2 + bw2 // 2, by2 + bh2 // 2),
                "确定", fill=0, font=fonts[28])
    bx3 = bx2 + bw2 + gap2
    draw.rounded_rectangle([bx3, by2, bx3 + bw2, by2 + bh2], radius=10,
                            outline=0, width=2)
    draw.text(_center(draw, "取消", fonts[28], bx3 + bw2 // 2, by2 + bh2 // 2),
                "取消", fill=0, font=fonts[28])

# 文字弹窗
def _draw_text_popup(draw, fonts, w, h, lines):
    box_w, box_h, cx2, cy2 = _popup_box(w, h)
    draw.rounded_rectangle([cx2, cy2, cx2 + box_w, cy2 + box_h], radius=20,
                            outline=0, width=3, fill=255)
    yy = cy2 + (box_h - len(lines) * px(h, POPUP_LINE_R)) // 2
    for line in lines:
        draw.text(_center(draw, line, fonts[36], cx2 + box_w // 2, yy),
                    line, fill=0, font=fonts[36])
        yy += px(h, POPUP_LINE_R)

# 保存配置
def _save(key, value):
    cfg = config.load()
    cfg[key] = value
    config.save(cfg)
    print(f"[设置] 已保存 {key}={value!r}")

# 唤起键盘输入
def _on_text_input(screen, fonts, key, itype):
    caps = NUM_CAPS if itype == "num" else STR_CAPS
    hint = "请输入数字" if itype == "num" else "请输入 API 地址"
    def on_submit(text):
        text = (text or "").strip()
        if not text:
            return None
        if itype == "num":
            try:
                v = max(1, int(text))
            except (TypeError, ValueError):
                return None
        else:
            v = text
        _save(key, v)
        return None
    return keyboard.start(screen, fonts, capabilities=caps, hint=hint,
                            enter_label="确定", owner="settings",
                            on_submit=on_submit)

# 触控输入
def handle(data, screen, fonts):
    if data["gesture"] != "tap":
        return None
    x, y = data["x-pixel"], data["y-pixel"]
    w, h = screen.output.resolution
    if STATE["cleaning"]:
        return None
    # 结果弹窗
    if STATE["popup"]:
        STATE["popup"] = None
        _show(screen, fonts)
        return None
    # 确认弹窗
    if STATE["confirm"]:
        box_w, box_h, cx2, cy2 = _popup_box(w, h)
        bw2, bh2 = px(w, 0.2), px(h, BTN_H_R)
        gap2 = px(w, 0.08)
        bx2 = cx2 + (box_w - 2 * bw2 - gap2) // 2
        by2 = cy2 + box_h * 0.6
        if _hit((bx2, by2, bw2, bh2), x, y):
            kind = STATE["confirm"]
            STATE["confirm"] = None
            if kind == "exit":
                cfg = config.load()
                cfg["token"], cfg["username"] = "", ""
                config.save(cfg)
                print("[设置] 已退出登录")
                _show(screen, fonts)
                return "home"
            if kind == "clean":
                print("[设置] 开始清理缓存")
                start_clean(screen, fonts)
                return None
            if kind == "sdr":
                print("[设置] 开始清理 kComics 文件夹的多余 sdr")
                start_clean_sdr(screen, fonts)
                return None
        if _hit((bx2 + bw2 + gap2, by2, bw2, bh2), x, y):
            STATE["confirm"] = None
            _show(screen, fonts)
            return None
        return None
    items = _all_items()
    # 设置项
    for idx, rect in _item_rects(w, h):
        if not _hit(rect, x, y):
            continue
        key, label, itype = items[idx]
        if itype == "exit":
            STATE["confirm"] = "exit"
            _show(screen, fonts)
            return None
        if itype == "clean":
            STATE["confirm"] = "clean"
            _show(screen, fonts)
            return None
        if itype == "sdr":
            if STATE["sdr_orphans"] is None:
                return None
            if not STATE["sdr_orphans"]:
                STATE["popup"] = ["无多余 sdr"]
                _show(screen, fonts)
                return None
            STATE["confirm"] = "sdr"
            _show(screen, fonts)
            return None
        if itype == "library":
            if STATE["library_on"] is None:
                return None
            toggle_library(screen, fonts)
            return None
        cfg = config.load()
        if itype == "bool":
            _save(key, not bool(cfg.get(key)))
            _show(screen, fonts)
        else:
            return _on_text_input(screen, fonts, key, itype)
        return None
    # 底部按键
    pages = _pages()
    rects = _bottom_rects(w, h)
    for label, action, rect in zip(
            ("上页", "返回", "下页"), ("up", "back", "down"), rects):
        if not _hit(rect, x, y):
            continue
        if action == "back":
            print("[设置] 返回主界面")
            return "home"
        if action == "up" and STATE["page"] > 0:
            STATE["page"] -= 1
            _show(screen, fonts)
            return None
        if action == "down" and STATE["page"] < pages - 1:
            STATE["page"] += 1
            _show(screen, fonts)
            return None
    return None

# 上屏
def _show(screen, fonts):
    try:
        screen.output.show(render(screen, fonts), is_flashing=bool(STATE["confirm"]))
    except OSError as e:
        print(f"[输出] 刷新失败:{e}")
