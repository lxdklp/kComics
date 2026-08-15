# 登录页
import config
from api import copymanga
from PIL import Image, ImageDraw
from ..layout import px
from .. import keyboard

TITLE = "登录"
MASK = "•"

STATE = {"username": "", "password": "", "busy": False, "popup": None,
            "show_pass": False}

# 布局比例
TITLE_Y_R = 0.09
BOX_X_R, BOX_W_R = 0.15, 0.7
USER_Y_R, PASS_Y_R = 0.22, 0.32
BOX_H_R = 0.065
LOGIN_BTN_Y_R, LOGIN_BTN_H_R = 0.43, 0.07
LABEL_W_R = 0.16          # 输入框内标签宽度
BACK_W_R, BACK_H_R = 0.195, 0.061   # 返回按钮
BACK_MARGIN_BOTTOM_R = 0.121
TOGGLE_X_R, TOGGLE_W_R = 0.86, 0.12   # 查看/隐藏密码切换按钮

# 键盘能力
USER_CAPS = ("en", "numsym")

def _wrap(text, n=16):
    return [text[i:i + n] for i in range(0, len(text), n)] or [text]

def _center(draw, text, font, cx, cy):
    bbox = draw.textbbox((0, 0), text, font=font)
    return (cx - (bbox[2] - bbox[0]) // 2 - bbox[0],
            cy - (bbox[3] - bbox[1]) // 2 - bbox[1])

#渲染
def render(screen, fonts):
    w, h = screen.output.resolution
    img = Image.new("L", (w, h), 255)
    draw = ImageDraw.Draw(img)
    draw.text(_center(draw, TITLE, fonts[96], w // 2, int(h * TITLE_Y_R)),
                TITLE, fill=0, font=fonts[96])
    box_w, box_h = px(w, BOX_W_R), px(h, BOX_H_R)
    boxes = (("user", "用户名", USER_Y_R), ("pass", "密码", PASS_Y_R))
    label_w = px(w, LABEL_W_R)
    for key, label, y_r in boxes:
        bx, by = px(w, BOX_X_R), px(h, y_r)
        draw.rounded_rectangle([bx, by, bx + box_w, by + box_h], radius=12,
                                outline=0, width=2)
        draw.text((bx + 10, by + (box_h - 36) // 2), label, fill=128, font=fonts[36])
        if key == "user":
            value = STATE["username"]
        else:
            value = STATE["password"] if STATE["show_pass"] else MASK * len(STATE["password"])
        if value:
            show = value[-16:]
            bbox = draw.textbbox((0, 0), show, font=fonts[48])
            ty = by + (box_h - (bbox[3] - bbox[1])) // 2 - bbox[1]
            draw.text((bx + label_w, ty), show, fill=0, font=fonts[48])
    # 查看/隐藏密码切换按钮
    tx, ty = px(w, TOGGLE_X_R), px(h, PASS_Y_R)
    tw, th = px(w, TOGGLE_W_R), px(h, BOX_H_R)
    draw.rounded_rectangle([tx, ty, tx + tw, ty + th], radius=12, outline=0, width=2)
    toggle_label = "隐藏" if STATE["show_pass"] else "查看"
    draw.text(_center(draw, toggle_label, fonts[28], tx + tw // 2, ty + th // 2),
                toggle_label, fill=0, font=fonts[28])
    # 登录按钮
    bw, bh = px(w, BOX_W_R), px(h, LOGIN_BTN_H_R)
    bx, by = px(w, BOX_X_R), px(h, LOGIN_BTN_Y_R)
    draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=12, outline=0, width=2)
    draw.text(_center(draw, "登录", fonts[48], bx + bw // 2, by + bh // 2),
                "登录", fill=0, font=fonts[48])
    # 返回按钮
    bw, bh = px(w, BACK_W_R), px(h, BACK_H_R)
    bx, by = (w - bw) // 2, h - px(h, BACK_MARGIN_BOTTOM_R) - bh
    draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=16, outline=0, width=2)
    draw.text(_center(draw, "返回", fonts[36], bx + bw // 2, by + bh // 2),
                "返回", fill=0, font=fonts[36])
    # 弹窗
    popup = STATE["popup"] if not STATE["busy"] else ["正在登录..."]
    if STATE["busy"] or popup:
        box_w2, box_h2 = px(w, 0.568), px(h, 0.146)
        cx2, cy2 = (w - box_w2) // 2, (h - box_h2) // 2
        draw.rounded_rectangle([cx2, cy2, cx2 + box_w2, cy2 + box_h2], radius=20,
                                outline=0, width=3, fill=255)
        yy = cy2 + (box_h2 - len(popup) * px(h, 0.0316)) // 2
        for line in popup:
            draw.text(_center(draw, line, fonts[36], cx2 + box_w2 // 2, yy),
                        line, fill=0, font=fonts[36])
            yy += px(h, 0.0316)
    return img

def _hit(rect, x, y):
    rx, ry, rw, rh = rect
    return rx <= x < rx + rw and ry <= y < ry + rh

# 登录
def _do_login(screen, fonts):
    username = STATE["username"].strip()
    password = STATE["password"]
    if not username or not password:
        STATE["popup"] = ["请输入用户名和密码"]
        _show(screen, fonts)
        return
    STATE["busy"] = True
    _show(screen, fonts)
    try:
        token = copymanga.login(username, password)
        cfg = config.load()
        cfg["username"], cfg["token"] = username, token
        config.save(cfg)
        STATE["popup"] = ["登录成功"]
    except Exception as e:
        STATE["popup"] = ["登录失败:"] + _wrap(str(e))
    STATE["busy"] = False
    _show(screen, fonts)

# 唤起键盘
def _start_user_kb(screen, fonts):
    def on_user(text):
        STATE["username"] = text
        return keyboard.start(screen, fonts,
                                capabilities=USER_CAPS, hint="请输入密码",
                                enter_label="完成", owner="login",
                                on_submit=_on_pass)
    return keyboard.start(screen, fonts,
                            capabilities=USER_CAPS, hint="请输入用户名",
                            enter_label="下一个", owner="login",
                            on_submit=on_user)

def _on_pass(text):
    STATE["password"] = text
    return None

# 触控处理
def handle(data, screen, fonts):
    if data["gesture"] != "tap":
        return None
    if STATE["busy"]:
        return None
    x, y = data["x-pixel"], data["y-pixel"]
    w, h = screen.output.resolution
    # 弹窗
    if STATE["popup"]:
        success = STATE["popup"][:1] == ["登录成功"]
        STATE["popup"] = None
        _show(screen, fonts)
        return "home" if success else None
    # 查看/隐藏密码切换
    tx, ty = px(w, TOGGLE_X_R), px(h, PASS_Y_R)
    tw, th = px(w, TOGGLE_W_R), px(h, BOX_H_R)
    if _hit((tx, ty, tw, th), x, y):
        STATE["show_pass"] = not STATE["show_pass"]
        _show(screen, fonts)
        return None
    # 输入框
    box_w, box_h = px(w, BOX_W_R), px(h, BOX_H_R)
    if _hit((px(w, BOX_X_R), px(h, USER_Y_R), box_w, box_h), x, y):
        return _start_user_kb(screen, fonts)
    if _hit((px(w, BOX_X_R), px(h, PASS_Y_R), box_w, box_h), x, y):
        return keyboard.start(screen, fonts,
                                capabilities=USER_CAPS, hint="请输入密码",
                                enter_label="完成", owner="login",
                                on_submit=_on_pass)
    # 登录按钮
    bw, bh = px(w, BOX_W_R), px(h, LOGIN_BTN_H_R)
    if _hit((px(w, BOX_X_R), px(h, LOGIN_BTN_Y_R), bw, bh), x, y):
        _do_login(screen, fonts)
        return None
    # 返回按钮
    bw, bh = px(w, BACK_W_R), px(h, BACK_H_R)
    bx, by = (w - bw) // 2, h - px(h, BACK_MARGIN_BOTTOM_R) - bh
    if _hit((bx, by, bw, bh), x, y):
        print("[登录] 返回主界面")
        return "home"
    return None

# 上屏
def _show(screen, fonts):
    try:
        screen.output.show(render(screen, fonts), is_flashing=bool(STATE["popup"]))
    except OSError as e:
        print(f"[输出] 刷新失败:{e}")
