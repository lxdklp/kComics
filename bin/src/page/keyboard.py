# 一个简单的触控键盘
#
# 调用方式(调用页 handle 内):
#   return keyboard.start(screen, fonts,
#       capabilities=('en', 'numsym'),   能力列表:cn 中文 | en 英文 |
#                                        numsym 数字+符号 | num 纯数字
#       hint='请输入用户名',              输入提示(空则显示"请输入内容")
#       enter_label='下一个',            回车键字符(空则"回车")
#       on_submit=回调,                  回车时回调(text);
#                                        返回动作字符串则继续导航,
#                                        否则清理会话回 owner
#       owner='login')                   取消/回车后返回的页面名
#
# 键盘页行为:
#   - 回车:on_submit(text),返回回调结果或 owner
#   - 取消:不回传内容,直接回 owner
#   - cap 键(仅 en):off(小写) → once(大写一次) → lock(大写锁定,反色) → off
#   - 含 cn 时显示拼音候选区(候选上屏/分页/空格上首选)
import os
import pickle

from PIL import Image, ImageDraw

from .layout import px

SESSION = {}

# 能力
MODE_LABEL = {"cn": "中文", "en": "英文", "numsym": "数字", "num": "数字"}
MODE_TAG = {"cn": "CN", "en": "EN", "numsym": "NUM", "num": "NUM"}

# 布局比例
INPUT_BOX_R = (0.0325, 0.0243, 0.935, 0.0789)   # 输入框 (x, y, w, h)
MARGIN_R = 0.0243                                # 键盘底边空隙
CAND_Y0_R = 0.1305                               # 候选区起点
CAND_GAP_X_R = 0.0097
CAND_GAP_Y_R = 0.0073
KEY_H_R = 0.094
KEY_GAP_R = 0.0073
STATUS_H_R = 0.024
TEXT_PAD_R = 0.0195
CURSOR_GAP_R = 0.0065

# 键盘按键
_LETTER_ROWS = (
    tuple((k, "letter", k, 1) for k in "qwertyuiop"),
    tuple((k, "letter", k, 1) for k in "asdfghjkl"),
    tuple((k, "letter", k, 1) for k in "zxcvbnm"),
)
_NUMSYM_ROWS = (
    tuple((k, "num", k, 1) for k in "1234567890"),
    tuple((k, "punct", k, 1) for k in (",", ".", "?", "!", ":", ";", ",", "(", ")")),
    tuple((k, "punct", k, 1) for k in ("-", "_", "+", "=", "@", "#", "%", "&", "*", "/")),
)
_NUM_ROWS = (
    tuple((k, "num", k, 1) for k in "123"),
    tuple((k, "num", k, 1) for k in "456"),
    tuple((k, "num", k, 1) for k in "789"),
)

def _num_fn_row():
    """纯数字第 4 行(运行时生成,enter 标签取自会话):取消/0/退格/确定."""
    return (("cancel", "cancel", "取消", 1),
            ("0", "num", "0", 1),
            ("bksp", "bksp", "退格", 1),
            ("enter", "enter", SESSION.get("enter_label") or "回车", 1))

def _fn_rows(mode, capabilities):
    """功能行:按模式与能力动态生成."""
    row = [("cancel", "cancel", "取消", 1)]
    if mode == "cn":
        row.append(("pageup", "pageup", "上页", 1))
        row.append(("pagedown", "pagedown", "下页", 1))
    if mode == "en":
        row.append(("cap", "cap", "cap", 1))
    if len(capabilities) > 1:
        row.append(("switch", "switch", "", 1))
    row.append(("bksp", "bksp", "退格", 1))
    row.append(("enter", "enter", SESSION.get("enter_label") or "回车", 2))
    return tuple(row)

def _rows(mode, capabilities):
    if mode == "cn" or mode == "en":
        return _LETTER_ROWS + (_fn_rows(mode, capabilities),)
    if mode == "numsym":
        return _NUMSYM_ROWS + (_fn_rows(mode, capabilities),)
    return _NUM_ROWS + (_num_fn_row(),)


def _mode_next(mode, capabilities):
    caps = list(capabilities)
    i = caps.index(mode) if mode in caps else 0
    return caps[(i + 1) % len(caps)]


# 拼音词库
_PINYIN_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "vendor", "pinyin")
_CHARS_CACHE = os.path.join(_PINYIN_DIR, "chars.pkl")      # 单字词典
_PHRASES_CACHE = os.path.join(_PINYIN_DIR, "phrases.pkl")  # 词组词典

PY = None
PHRASES = None

# 加载词典
def _load_pkl(path, label):
    try:
        with open(path, "rb") as f:
            cached = pickle.load(f)
        d = cached.get("dict") if isinstance(cached, dict) else None
        if isinstance(d, dict):
            print(f"[拼音] 读取{label} {path} ({len(d)} 键)")
            return d
    except (OSError, EOFError, pickle.UnpicklingError, AttributeError, ValueError) as e:
        print(f"[拼音] {label}读取失败:{e}")
    print(f"[拼音] {label}{path} 不可用,返回空词典")
    return {}

# 单字
def get_chars_dict():
    global PY
    if PY is None:
        PY = _load_pkl(_CHARS_CACHE, "单字词库")
        print(f"[拼音] 已加载单字词库 {len(PY)} 个音节")
    return PY

# 词组
def get_phrases():
    global PHRASES
    if PHRASES is None:
        PHRASES = _load_pkl(_PHRASES_CACHE, "词组词库")
        print(f"[拼音] 已加载词组词库 {len(PHRASES)} 个拼音键")
    return PHRASES

# 候选来源
def _cand_kind():
    py = SESSION.get("pinyin", "")
    if not py:
        return None
    if get_chars_dict().get(py):
        return 'char'
    if get_phrases().get(py):
        return 'phrase'
    return None

# 候选页
def _per_page(kind=None):
    """候选每页数:单字 5x4=20,词组 3x4=12."""
    kind = kind or _cand_kind()
    return 12 if kind == 'phrase' else 20

# 候选词
def _candidates():
    kind = _cand_kind()
    if not kind:
        return []
    py = SESSION.get("pinyin", "")
    if kind == 'char':
        return get_chars_dict().get(py, [])
    return get_phrases().get(py, [])

# 当前页候选词
def _current_candidates():
    all_c = _candidates()
    start = SESSION.get("page", 0) * _per_page()
    return all_c[start:start + _per_page()]


# 布局
def _layout(w, h):
    mode = SESSION["mode"]
    rows = _rows(mode, SESSION["capabilities"])
    x0 = px(w, INPUT_BOX_R[0])
    x1 = px(w, INPUT_BOX_R[0] + INPUT_BOX_R[2])
    key_h = px(h, KEY_H_R)
    key_gap = px(h, KEY_GAP_R)
    key_h_total = len(rows) * key_h + (len(rows) - 1) * key_gap
    key_y0 = h - px(h, MARGIN_R) - key_h_total
    status_h = px(h, STATUS_H_R)
    status_y = key_y0 - status_h - key_gap
    out = []
    for r, row in enumerate(rows):
        weights = [k[3] for k in row]
        total_w = sum(weights)
        unit = (x1 - x0 - (len(row) - 1) * key_gap) / total_w
        row_w = sum(unit * weight for weight in weights) + (len(row) - 1) * key_gap
        x = x0 + (x1 - x0 - row_w) // 2
        y = key_y0 + r * (key_h + key_gap)
        for (kid, ktype, label, weight) in row:
            kw = int(unit * weight)
            out.append((kid, ktype, label, (x, y, kw, key_h)))
            x += kw + key_gap
    cand_gap_x = px(w, CAND_GAP_X_R)
    cand_gap_y = px(h, CAND_GAP_Y_R)
    cand_y0 = px(h, CAND_Y0_R)
    cand_h = (status_y - cand_y0 - 3 * cand_gap_y) // 4
    kind = _cand_kind()
    ncol = 3 if kind == 'phrase' else 5
    per_page = 12 if kind == 'phrase' else 20
    cw = (x1 - x0 - (ncol - 1) * cand_gap_x) // ncol
    cand_rects = []
    for i in range(per_page):
        r, c = divmod(i, ncol)
        cand_rects.append((x0 + c * (cw + cand_gap_x),
                           cand_y0 + r * (cand_h + cand_gap_y), cw, cand_h))
    return {"keys": out, "cand_rects": cand_rects,
            "status_y": status_y, "status_h": status_h}

def _center(draw, text, font, cx, cy):
    bbox = draw.textbbox((0, 0), text, font=font)
    return (cx - (bbox[2] - bbox[0]) // 2 - bbox[0],
            cy - (bbox[3] - bbox[1]) // 2 - bbox[1])

def _hit(rect, x, y):
    rx, ry, rw, rh = rect
    return rx <= x < rx + rw and ry <= y < ry + rh

# 会话
def start(screen, fonts, *, capabilities, hint='', enter_label='',
            on_submit=None, owner=''):
    # 调用页 handle 内调用, 写入会话并返回 'keyboard' 供导航
    caps = tuple(capabilities) if capabilities else ('en',)
    SESSION.clear()
    SESSION.update(
        capabilities=caps,
        hint=hint or '请输入内容',
        enter_label=enter_label or '回车',
        on_submit=on_submit,
        owner=owner,
        text='', pinyin='', mode=caps[0], cap='off',
        page=0, popup=None)
    return 'keyboard'

#渲染
def render(screen, fonts):
    w, h = screen.output.resolution
    img = Image.new("L", (w, h), 255)
    draw = ImageDraw.Draw(img)
    x0, y0 = px(w, INPUT_BOX_R[0]), px(h, INPUT_BOX_R[1])
    bw, bh = px(w, INPUT_BOX_R[2]), px(h, INPUT_BOX_R[3])
    # 输入框
    draw.rounded_rectangle([x0, y0, x0 + bw, y0 + bh], radius=16, outline=0, width=3)
    text = SESSION.get("text", "")
    pad = px(w, TEXT_PAD_R)
    if text:
        show = text[-18:] if len(text) > 18 else text
        bbox = draw.textbbox((0, 0), show, font=fonts[48])
        ty = y0 + (bh - (bbox[3] - bbox[1])) // 2 - bbox[1]
        draw.text((x0 + pad, ty), show, fill=0, font=fonts[48])
        cursor_x = x0 + pad + (bbox[2] - bbox[0]) + px(w, CURSOR_GAP_R)
        draw.rectangle([cursor_x, ty + bbox[1] + 4, cursor_x + 4, ty + bbox[3]], fill=0)
    else:
        hint = SESSION.get("hint") or "请输入内容"
        bbox = draw.textbbox((0, 0), hint, font=fonts[28])
        draw.text((x0 + pad, y0 + (bh - (bbox[3] - bbox[1])) // 2 - bbox[1]),
                    hint, fill=128, font=fonts[28])
    lay = _layout(w, h)
    mode = SESSION["mode"]
    # 候选区
    all_c = []
    if mode == "cn":
        cands = _current_candidates()
        all_c = _candidates()
        if not all_c and SESSION.get("pinyin"):
            draw.text((x0 + px(w, TEXT_PAD_R), px(h, CAND_Y0_R) + px(h, MARGIN_R)),
                        f"“{SESSION['pinyin']}”无匹配拼音", fill=128, font=fonts[28])
        for i, cand in enumerate(cands):
            rx, ry, rw, rh = lay["cand_rects"][i]
            draw.rounded_rectangle([rx, ry, rx + rw, ry + rh], radius=12,
                                    outline=0, width=2)
            draw.text(_center(draw, cand, fonts[48], rx + rw // 2, ry + rh // 2),
                        cand, fill=0, font=fonts[48])
    # 状态行
    mode_label = MODE_LABEL.get(mode, mode)
    cap_label = ""
    if mode == "en":
        cap_label = {"off": "", "once": "  大写开", "lock": "  大写锁定"}.get(
            SESSION.get("cap", "off"), "")
    py_label = f"  拼音:{SESSION['pinyin']}" if SESSION.get("pinyin") else ""
    page_label = ""
    if mode == "cn" and all_c:
        pages = (len(all_c) + _per_page() - 1) // _per_page()
        if pages > 1:
            page_label = f"  候选 {SESSION.get('page', 0) + 1}/{pages}页"
    status_ty = lay["status_y"] + (lay["status_h"] - 28) // 2
    draw.text((x0 + px(w, TEXT_PAD_R), status_ty),
                f"模式:{mode_label}{cap_label}{py_label}{page_label}",
                fill=0, font=fonts[28])
    # 键盘
    for (kid, ktype, label, (rx, ry, rw, rh)) in lay["keys"]:
        show: str = label
        fill = 0
        if ktype == "letter":
            show = label.upper() if SESSION.get("cap", "off") != "off" else label
        elif ktype == "switch":
            nxt = _mode_next(mode, SESSION["capabilities"])
            show = MODE_TAG.get(nxt) or nxt.upper()
        elif ktype == "cap":
            cap = SESSION.get("cap", "off")
            show = "CAP" if cap != "off" else "cap"
            if cap == "lock":
                fill = 255
                draw.rounded_rectangle([rx, ry, rx + rw, ry + rh], radius=12,
                                        fill=0, width=2)
        if fill != 255:
            draw.rounded_rectangle([rx, ry, rx + rw, ry + rh], radius=12,
                                    outline=0, width=2)
        draw.text(_center(draw, show, fonts[36], rx + rw // 2, ry + rh // 2),
                    show, fill=fill, font=fonts[36])
    return img

# 触控输入
def handle(data, screen, fonts):
    if data["gesture"] != "tap":
        return None
    x, y = data["x-pixel"], data["y-pixel"]
    w, h = screen.output.resolution
    if not SESSION:
        return None
    mode = SESSION["mode"]
    keys = _layout(w, h)["keys"]
    # 候选上屏
    if mode == "cn":
        for i, rect in enumerate(_layout(w, h)["cand_rects"]):
            if _hit(rect, x, y) and i < len(_current_candidates()):
                cand = _current_candidates()[i]
                print(f"[键盘] 上屏候选 {cand}")
                SESSION["text"] += cand
                SESSION["pinyin"] = ""
                SESSION["page"] = 0
                _show(screen, fonts)
                return None
    for (kid, ktype, label, rect) in keys:
        if not _hit(rect, x, y):
            continue
        if ktype == "letter":
            if mode == "cn":
                SESSION["pinyin"] += kid
                SESSION["page"] = 0
            else:
                ch = kid.upper() if SESSION.get("cap", "off") != "off" else kid
                SESSION["text"] += ch
                if SESSION.get("cap") == "once":
                    SESSION["cap"] = "off"
        elif ktype == "num" or ktype == "punct":
            SESSION["text"] += label
        elif ktype == "cancel":
            owner = SESSION.get("owner") or "home"
            SESSION.clear()
            return owner
        elif ktype == "pageup":
            if mode == "cn" and _candidates():
                SESSION["page"] = max(0, SESSION.get("page", 0) - 1)
        elif ktype == "pagedown":
            if mode == "cn" and _candidates():
                n = len(_candidates())
                pages = (n + _per_page() - 1) // _per_page()
                SESSION["page"] = min(pages - 1, SESSION.get("page", 0) + 1)
        elif ktype == "cap":
            if mode == "en":
                cur = SESSION.get("cap", "off")
                SESSION["cap"] = {"off": "once", "once": "lock", "lock": "off"}[cur]
        elif ktype == "switch":
            SESSION["mode"] = _mode_next(mode, SESSION["capabilities"])
            SESSION["cap"] = "off"
            SESSION["page"] = 0
            if mode == "cn":
                SESSION["pinyin"] = ""
        elif ktype == "bksp":
            if SESSION.get("pinyin"):
                SESSION["pinyin"] = SESSION["pinyin"][:-1]
                SESSION["page"] = 0
            else:
                SESSION["text"] = SESSION["text"][:-1]
        elif ktype == "enter":
            text = SESSION.get("text", "")
            cb = SESSION.get("on_submit")
            if cb is not None:
                try:
                    action = cb(text)
                except Exception as e:
                    print(f"[键盘] 回调异常:{type(e).__name__}: {e}")
                    action = None
            else:
                action = None
            if action:
                return action
            owner = SESSION.get("owner") or "home"
            SESSION.clear()
            return owner
        _show(screen, fonts)
        return None
    return None

# 上屏
def _show(screen, fonts):
    try:
        screen.output.show(render(screen, fonts), is_flashing=False)
    except OSError as e:
        print(f"[输出] 刷新失败:{e}")
