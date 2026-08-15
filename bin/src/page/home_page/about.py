# 关于
import json
import os
import threading
from PIL import Image, ImageDraw
from ..layout import px

TITLE = "关于"
NOTE = "Kindle 的开源漫画客户端"
CHECK_LABEL = "检测更新"
ACK_TITLE = "鸣谢"
ACK_JSON = "acknowledgments.json"
PER_PAGE = 8

STATE = {"page": 0, "checking": False, "popup": None}

# 布局比例
TITLE_Y_R = 0.12
VERSION_Y_R = 0.19
NOTE_Y_R = 0.235
CHECK_Y_R = 0.29           # 检测更新按钮中心
CHECK_W_R, CHECK_H_R = 0.3, 0.05
ACK_TITLE_Y_R = 0.38
ACK_Y0_R = 0.44
ACK_CARD_H_R = 0.05         # 单张卡片高度
ACK_CARD_GAP_R = 0.004       # 卡片间距
BTN_W_R, BTN_H_R = 0.24, 0.06
BTN_GAP_R = 0.02
BTN_Y_R = 0.90
POPUP_W_R, POPUP_H_R = 0.568, 0.2
POPUP_LINE_R = 0.04

# 返回 bin 目录
def _bin_dir():
    return os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))

# 加载鸣谢清单
def _load_acks():
    path = os.path.join(_bin_dir(), ACK_JSON)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        items = data.get("acknowledgments") or []
        return [i for i in items if isinstance(i, dict) and i.get("name")]
    except (OSError, ValueError) as e:
        print(f"[关于] 读取鸣谢清单失败:{type(e).__name__}: {e}")
        return []

# 计算总页数
def _pages():
    n = len(_load_acks())
    return (n + PER_PAGE - 1) // PER_PAGE if n else 1

# 计算文本居中坐标
def _center(draw, text, font, cx, cy):
    bbox = draw.textbbox((0, 0), text, font=font)
    return (cx - (bbox[2] - bbox[0]) // 2 - bbox[0],
            cy - (bbox[3] - bbox[1]) // 2 - bbox[1])

# 计算文本截断
def _fit(draw, text, font, max_w):
    if draw.textlength(text, font=font) <= max_w:
        return text
    while text and draw.textlength(text + "…", font=font) > max_w:
        text = text[:-1]
    return text + "…"

# 计算弹窗
def _popup_box(w, h):
    box_w, box_h = px(w, POPUP_W_R), px(h, POPUP_H_R)
    return box_w, box_h, (w - box_w) // 2, (h - box_h) // 2

# 计算文本弹窗坐标
def _draw_text_popup(draw, fonts, w, h, lines):
    box_w, box_h, cx2, cy2 = _popup_box(w, h)
    draw.rounded_rectangle([cx2, cy2, cx2 + box_w, cy2 + box_h], radius=20,
                           outline=0, width=3, fill=255)
    yy = cy2 + (box_h - len(lines) * px(h, POPUP_LINE_R)) // 2
    for line in lines:
        draw.text(_center(draw, line, fonts[36], cx2 + box_w // 2, yy),
                  line, fill=0, font=fonts[36])
        yy += px(h, POPUP_LINE_R)

# 检测更新按钮
def _check_rect(w, h):
    bw, bh = px(w, CHECK_W_R), px(h, CHECK_H_R)
    return ((w - bw) // 2, int(h * CHECK_Y_R) - bh // 2, bw, bh)

# 检查更新
def start_check(screen, fonts):
    if STATE["checking"]:
        return
    STATE["checking"] = True
    STATE["popup"] = None
    _show(screen, fonts)
    def _run():
        from kcomics import BUILD, VERSION
        try:
            from api.lapi import check_update, UpdateError
        except Exception as e:
            print(f"[更新] 模块导入失败:{type(e).__name__}: {e}")
            STATE["popup"] = ["检查更新失败", "模块导入失败"]
            STATE["checking"] = False
            _show(screen, fonts)
            return
        try:
            new_build = check_update()
        except UpdateError as e:
            print(f"[更新] 检查失败:{e}")
            STATE["popup"] = ["检查更新失败"] + _wrap(str(e))[:2]
        except Exception as e:
            print(f"[更新] 检查异常:{type(e).__name__}: {e}")
            STATE["popup"] = ["检查更新失败"] + _wrap(str(e))[:2]
        else:
            if new_build > BUILD:
                print(f"[更新] 发现新版本 build {new_build}(当前 {BUILD})")
                STATE["popup"] = [f"发现新版本 kComics {VERSION}({new_build})"]
            else:
                print(f"[更新] 已为最新版本(build {BUILD})")
                STATE["popup"] = ["已为最新版本"]
        STATE["checking"] = False
        _show(screen, fonts)
    threading.Thread(target=_run, daemon=True).start()

# 按键矩形
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

# 渲染
def render(screen, fonts):
    from kcomics import VERSION, BUILD
    w, h = screen.output.resolution
    img = Image.new("L", (w, h), 255)
    draw = ImageDraw.Draw(img)
    draw.text(_center(draw, TITLE, fonts[96], w // 2, int(h * TITLE_Y_R)),
                TITLE, fill=0, font=fonts[96])
    ver_text = f"kComics {VERSION}({BUILD})"
    draw.text(_center(draw, ver_text, fonts[36], w // 2, int(h * VERSION_Y_R)),
                ver_text, fill=0, font=fonts[36])
    draw.text(_center(draw, NOTE, fonts[36], w // 2, int(h * NOTE_Y_R)),
                NOTE, fill=0, font=fonts[36])
    crx, cry, crw, crh = _check_rect(w, h)
    draw.rounded_rectangle([crx, cry, crx + crw, cry + crh], radius=12,
                            outline=0, width=2)
    draw.text(_center(draw, CHECK_LABEL, fonts[36], crx + crw // 2, cry + crh // 2),
                CHECK_LABEL, fill=0, font=fonts[36])
    acks = _load_acks()
    if acks:
        draw.text(_center(draw, ACK_TITLE, fonts[48], w // 2, int(h * ACK_TITLE_Y_R)),
                    ACK_TITLE, fill=0, font=fonts[48])
        pages = (len(acks) + PER_PAGE - 1) // PER_PAGE
        if STATE["page"] >= pages:
            STATE["page"] = 0
        start = STATE["page"] * PER_PAGE
        card_w = w - 2 * px(w, 0.05)
        card_h = px(h, ACK_CARD_H_R)
        gap = px(h, ACK_CARD_GAP_R)
        y = int(h * ACK_Y0_R)
        name_font, info_font = fonts[36], fonts[28]
        lx = px(w, 0.075)
        text_w = card_w - 2 * (lx - px(w, 0.05))
        for i in range(PER_PAGE):
            idx = start + i
            if idx >= len(acks):
                break
            item = acks[idx]
            draw.rounded_rectangle(
                [px(w, 0.05), y, px(w, 0.05) + card_w, y + card_h],
                radius=14, outline=0, width=2)
            text = _fit(draw, item.get("name", ""), name_font, text_w)
            bbox = draw.textbbox((0, 0), text, font=name_font)
            draw.text((lx, y + px(h, 0.004) - bbox[1]), text, fill=0, font=name_font)
            info = item.get("info") or ""
            if info:
                info = _fit(draw, info, info_font, text_w)
                ib = draw.textbbox((0, 0), info, font=info_font)
                draw.text((lx + text_w - (ib[2] - ib[0]) - ib[0],
                            y + px(h, 0.004) - ib[1] + 4),
                            info, fill=128, font=info_font)
            url = item.get("url") or ""
            if url:
                url = _fit(draw, url, info_font, text_w)
                ub = draw.textbbox((0, 0), url, font=info_font)
                draw.text((lx, y + card_h - px(h, 0.004) - (ub[3] - ub[1]) - ub[1]),
                            url, fill=160, font=info_font)
            y += card_h + gap
    pages = _pages()
    rects = _bottom_rects(w, h)
    for label, action, rect in zip(("上页", "返回", "下页"), ("up", "back", "down"), rects):
        enabled = not ((action == "up" and STATE["page"] == 0)
                        or (action == "down" and STATE["page"] >= pages - 1))
        rx, ry, rw, rh = rect
        draw.rounded_rectangle([rx, ry, rx + rw, ry + rh], radius=12,
                                outline=0, width=2)
        draw.text(_center(draw, label, fonts[36], rx + rw // 2, ry + rh // 2),
                    label, fill=0 if enabled else 160, font=fonts[36])
    by = px(h, BTN_Y_R) + px(h, BTN_H_R)
    page_text = f"{STATE['page'] + 1}/{pages}页"
    draw.text(_center(draw, page_text, fonts[28], w // 2, by + px(h, 0.03)),
                page_text, fill=128, font=fonts[28])
    if STATE["checking"]:
        _draw_text_popup(draw, fonts, w, h, ["正在检查更新…"])
    elif STATE["popup"]:
        _draw_text_popup(draw, fonts, w, h, STATE["popup"])
    return img

# 触控输入
def handle(data, screen, fonts):
    if data["gesture"] != "tap":
        return None
    x, y = data["x-pixel"], data["y-pixel"]
    w, h = screen.output.resolution
    if STATE["popup"]:
        STATE["popup"] = None
        _show(screen, fonts)
        return None
    # 检测更新按钮
    crx, cry, crw, crh = _check_rect(w, h)
    if not STATE["checking"] and crx <= x < crx + crw and cry <= y < cry + crh:
        print("[关于] 开始检查更新")
        start_check(screen, fonts)
        return None
    pages = _pages()
    rects = _bottom_rects(w, h)
    for label, action, rect in zip(("上页", "返回", "下页"), ("up", "back", "down"), rects):
        rx, ry, rw, rh = rect
        if rx <= x < rx + rw and ry <= y < ry + rh:
            if action == "back":
                print("[关于] 返回主界面")
                return "home"
            if action == "up" and STATE["page"] > 0:
                STATE["page"] -= 1
            if action == "down" and STATE["page"] < pages - 1:
                STATE["page"] += 1
            try:
                screen.output.show(render(screen, fonts), is_flashing=False)
            except OSError as e:
                print(f"[输出] 刷新失败:{e}")
            return None
    return None

def _wrap(text, n=16):
    return [text[i:i + n] for i in range(0, len(text), n)] or [text]

# 上屏
def _show(screen, fonts):
    try:
        screen.output.show(render(screen, fonts),
                            is_flashing=bool(STATE["checking"] or STATE["popup"]))
    except OSError as e:
        print(f"[输出] 刷新失败:{e}")
