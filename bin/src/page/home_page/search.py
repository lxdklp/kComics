# 搜索页
import threading
from api import copymanga
from PIL import Image, ImageDraw
from ..layout import px
from .. import keyboard

TITLE = "搜索"

_SEARCH_GEN = 0
_SHOW_LOCK = threading.Lock()
_NAVIGATE = None

# 布局比例
SEARCH_BOX_R = (0.0325, 0.0243, 0.935, 0.0789)  # 搜索框 (x, y, w, h)
TEXT_PAD_R = 0.0195
CURSOR_GAP_R = 0.0065
POPUP_W_R, POPUP_H_R = 0.568, 0.146
POPUP_LINE_R = 0.0316

PLACEHOLDER = "点击输入漫画名称..."

# 键盘能力
SEARCH_CAPS = ("cn", "en", "numsym")

# 返回按钮比例
BACK_W_R, BACK_H_R = 0.195, 0.061
BACK_MARGIN_BOTTOM_R = 0.121

# 页面切换回调
def set_navigate(fn):
    global _NAVIGATE
    _NAVIGATE = fn


# 页面状态
STATE = {"text": "", "popup": None}

def _center(draw, text, font, cx, cy):
    bbox = draw.textbbox((0, 0), text, font=font)
    return (cx - (bbox[2] - bbox[0]) // 2 - bbox[0],
            cy - (bbox[3] - bbox[1]) // 2 - bbox[1])

# 渲染
def render(screen, fonts):
    w, h = screen.output.resolution
    img = Image.new("L", (w, h), 255)
    draw = ImageDraw.Draw(img)
    x0, y0 = px(w, SEARCH_BOX_R[0]), px(h, SEARCH_BOX_R[1])
    bw, bh = px(w, SEARCH_BOX_R[2]), px(h, SEARCH_BOX_R[3])
    # 搜索框
    draw.rounded_rectangle([x0, y0, x0 + bw, y0 + bh], radius=16, outline=0, width=3)
    text = STATE["text"]
    pad = px(w, TEXT_PAD_R)
    if text:
        show = text[-18:] if len(text) > 18 else text
        bbox = draw.textbbox((0, 0), show, font=fonts[48])
        ty = y0 + (bh - (bbox[3] - bbox[1])) // 2 - bbox[1]
        draw.text((x0 + pad, ty), show, fill=0, font=fonts[48])
        cursor_x = x0 + pad + (bbox[2] - bbox[0]) + px(w, CURSOR_GAP_R)
        draw.rectangle([cursor_x, ty + bbox[1] + 4, cursor_x + 4, ty + bbox[3]], fill=0)
    else:
        bbox = draw.textbbox((0, 0), PLACEHOLDER, font=fonts[28])
        draw.text((x0 + pad, y0 + (bh - (bbox[3] - bbox[1])) // 2 - bbox[1]),
                    PLACEHOLDER, fill=128, font=fonts[28])
    # 提示文本
    draw.text(_center(draw, "点击搜索框开始输入", fonts[36], w // 2, int(h * 0.35)),
                "点击搜索框开始输入", fill=128, font=fonts[36])
    # 返回按钮
    bw, bh = px(w, BACK_W_R), px(h, BACK_H_R)
    bx, by = (w - bw) // 2, h - px(h, BACK_MARGIN_BOTTOM_R) - bh
    draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=16, outline=0, width=2)
    draw.text(_center(draw, "返回", fonts[36], bx + bw // 2, by + bh // 2),
                "返回", fill=0, font=fonts[36])
    # 弹窗
    if STATE["popup"]:
        lines = STATE["popup"]
        box_w, box_h = px(w, POPUP_W_R), px(h, POPUP_H_R)
        bx, by = (w - box_w) // 2, (h - box_h) // 2
        draw.rounded_rectangle([bx, by, bx + box_w, by + box_h], radius=20,
                                outline=0, width=3, fill=255)
        yy = by + (box_h - len(lines) * px(h, POPUP_LINE_R)) // 2
        for line in lines:
            draw.text(_center(draw, line, fonts[36], bx + box_w // 2, yy),
                        line, fill=0, font=fonts[36])
            yy += px(h, POPUP_LINE_R)
    return img

def _hit(rect, x, y):
    rx, ry, rw, rh = rect
    return rx <= x < rx + rw and ry <= y < ry + rh

def _wrap(text, n=16):
    return [text[i:i + n] for i in range(0, len(text), n)] or [text]

# 处理键盘输入
def _on_query(screen, fonts, query):
    global _SEARCH_GEN
    STATE["text"] = query
    if not query.strip():
        STATE["popup"] = ["请输入搜索内容"]
        _show(screen, fonts)
        return None
    STATE["popup"] = [f"搜索:{query}", "搜索中..."]
    _show(screen, fonts)
    gen = _SEARCH_GEN
    def _run():
        try:
            items = copymanga.search_comics(query, limit=30)
        except Exception as e:
            print(f"[搜索] 搜索异常:{type(e).__name__}: {e}")
            if gen == _SEARCH_GEN:
                STATE["popup"] = ["搜索失败:"] + _wrap(str(e))
                _show(screen, fonts)
            return
        print(f"[搜索] 搜索到 {len(items)} 条结果")
        if gen == _SEARCH_GEN:
            from .search_page import result
            STATE["popup"] = None
            result.STATE.update(query=query, list=items, page=0, popup=None)
            if _NAVIGATE is not None:
                _NAVIGATE("result")
            else:
                _show(screen, fonts)
    threading.Thread(target=_run, daemon=True).start()
    return None

# 触控处理
def handle(data, screen, fonts):
    if data["gesture"] != "tap":
        return None
    x, y = data["x-pixel"], data["y-pixel"]
    w, h = screen.output.resolution
    if STATE["popup"]:
        print("[搜索] 关闭弹窗")
        STATE["popup"] = None
        _show(screen, fonts)
        return None
    # 搜索框
    x0, y0 = px(w, SEARCH_BOX_R[0]), px(h, SEARCH_BOX_R[1])
    bw, bh = px(w, SEARCH_BOX_R[2]), px(h, SEARCH_BOX_R[3])
    if _hit((x0, y0, bw, bh), x, y):
        print("[搜索] 唤起键盘")
        return keyboard.start(screen, fonts,
                                capabilities=SEARCH_CAPS, hint="请输入漫画名称",
                                enter_label="搜索", owner="search",
                                on_submit=lambda t: _on_query(screen, fonts, t))
    # 返回按钮
    bw, bh = px(w, BACK_W_R), px(h, BACK_H_R)
    bx, by = (w - bw) // 2, h - px(h, BACK_MARGIN_BOTTOM_R) - bh
    if _hit((bx, by, bw, bh), x, y):
        print("[搜索] 返回主界面")
        return "home"
    return None

# 上屏
def _show(screen, fonts):
    with _SHOW_LOCK:
        try:
            screen.output.show(render(screen, fonts), is_flashing=bool(STATE["popup"]))
        except OSError as e:
            print(f"[输出] 刷新失败:{e}")
