# 主页
import config
from PIL import Image, ImageDraw
from .layout import px

TITLE = "kComics"
BUTTONS = (
    ("login", "登录"),
    ("search", "搜索"),
    ("settings", "设置"),
    ("about", "关于"),
    ("exit", "退出"),
)

# 布局比例
BTN_W_R, BTN_H_R = 0.487, 0.085   # 按钮宽=屏宽49%,高=屏高8.5%
BTN_GAP_R = 0.036                 # 按钮间距=屏高3.6%
BTN_MARGIN_BOTTOM_R = 0.109       # 按钮组底部空隙=屏高10.9%
TITLE_Y_R = 0.15                  # 标题中心 y=屏高15%

# 检查登录
def _logged_in():
    return bool(config.get_token())

# 按钮列表
def _buttons():
    btns = list(BUTTONS)
    btns[0] = ("favorites", "收藏") if _logged_in() else ("login", "登录")
    return btns

# 计算按钮矩形区域
def button_rects(screen):
    w, h = screen.output.resolution
    bw, bh = px(w, BTN_W_R), px(h, BTN_H_R)
    gap = px(h, BTN_GAP_R)
    bx = (w - bw) // 2
    btns = _buttons()
    total = len(btns) * bh + (len(btns) - 1) * gap
    start = h - total - px(h, BTN_MARGIN_BOTTOM_R)
    rects = {}
    for i, (key, _) in enumerate(btns):
        rects[key] = (bx, start + i * (bh + gap), bw, bh)
    return rects

# 绘制文本
def _center_text(draw, text, font, cx, cy):
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    return (cx - tw // 2 - bbox[0], cy - th // 2 - bbox[1])

# 渲染主界面
def render(screen, fonts):
    w, h = screen.output.resolution
    img = Image.new("L", (w, h), 255)
    draw = ImageDraw.Draw(img)

    title_font = fonts[96]
    draw.text(_center_text(draw, TITLE, title_font, w // 2, int(h * TITLE_Y_R)),
                TITLE, fill=0, font=title_font)

    btn_font = fonts[48]
    rects = button_rects(screen)
    for key, label in _buttons():
        x, y, bw, bh = rects[key]
        draw.rounded_rectangle([x, y, x + bw, y + bh], radius=16, outline=0, width=2)
        draw.text(_center_text(draw, label, btn_font, x + bw // 2, y + bh // 2),
                    label, fill=0, font=btn_font)
    try:
        cfg = config.load()
    except Exception:
        cfg = {}
    if cfg.get("token"):
        acct = cfg.get("username") or "已登录"
        hint = f"账号:{acct}"
    else:
        hint = "未登录"
    draw.text(_center_text(draw, hint, fonts[28], w // 2, int(h * 0.26)),
                hint, fill=128, font=fonts[28])
    return img

# 触屏输入
def handle(data, screen, fonts):
    if data["gesture"] != "tap":
        return None
    x, y = data["x-pixel"], data["y-pixel"]
    for key, (rx, ry, rw, rh) in button_rects(screen).items():
        if rx <= x < rx + rw and ry <= y < ry + rh:
            print(f"[主界面] 点击按钮 {key}")
            return key
    return None
