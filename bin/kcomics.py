import os
import sys
import threading
import time

_BIN = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_BIN, "vendor"))
sys.path.insert(0, os.path.join(_BIN, "src"))

from screen import Screen
from PIL import Image, ImageDraw, ImageFont

import config
from page import home
from page import keyboard
from page.home_page import about, favorites, login, search, settings
from page.home_page.search_page import result
from page.home_page.search_page.result_page import info

# 一些常量
FONT_PATH = "/usr/java/lib/fonts/STHeitiMedium.ttf"
VERSION = "v1.0.0"
BUILD = 1

# 页面注册表
PAGES = {
    "home": (home.render, home.handle),
    "login": (login.render, login.handle),
    "search": (search.render, search.handle),
    "favorites": (favorites.render, favorites.handle),
    "keyboard": (keyboard.render, keyboard.handle),
    "result": (result.render, result.handle),
    "info": (info.render, info.handle),
    "settings": (settings.render, settings.handle),
    "about": (about.render, about.handle),
}

screen = None
fonts = {}

# 加载字体
def load_fonts():
    """加载所需字号的中文字体,缺失时降级默认字体."""
    result = {}
    for size in (96, 48, 36, 28):
        try:
            result[size] = ImageFont.truetype(FONT_PATH, size)
        except OSError:
            print(f"[字体] {FONT_PATH} 不存在,使用默认字体")
            result[size] = ImageFont.load_default()
            break
    return result

# 渲染并显示页面
def show_page(name, flashing=True):
    """渲染并整屏显示指定页面,返回渲染的图像."""
    render_fn = PAGES[name][0]
    image = render_fn(screen, fonts)
    try:
        assert screen is not None
        marker = screen.output.show(image, is_flashing=flashing)
        print(f"[输出] 显示页面 {name},marker={marker}")
    except OSError as e:
        print(f"[输出] 刷新失败:{e}")
    return image

# 绘制弹窗图像
def draw_popup(lines):
    """绘制居中弹窗图像:白色背景 + 圆角框 + 居中文本."""
    assert screen is not None
    w, h = screen.output.resolution
    img = Image.new("L", (w, h), 255)
    draw = ImageDraw.Draw(img)
    if isinstance(lines, str):
        lines = [lines]
    body_font = fonts[36]
    box_w, box_h = int(w * 0.487), int(h * 0.133)   # 弹窗屏宽 48.7%,屏高 13.3%
    line_h = int(h * 0.0316)                        # 行距屏高 3.16%
    bx, by = (w - box_w) // 2, (h - box_h) // 2
    draw.rounded_rectangle([bx, by, bx + box_w, by + box_h], radius=20, outline=0, width=3)
    y = by + (box_h - len(lines) * line_h) // 2
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=body_font)
        draw.text((bx + (box_w - (bbox[2] - bbox[0])) // 2 - bbox[0], y),
                    line, fill=0, font=body_font)
        y += line_h
    return img

# 主函数
def main():
    global screen, fonts
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                getattr(stream, "reconfigure")(line_buffering=True)
            except (OSError, ValueError):
                pass
    if "--probe" in sys.argv:
        from screen.output.framebuffer import probe_epdc # type: ignore
        sys.exit(probe_epdc())
    screen = Screen()
    if not screen.input.initialization():
        print("触摸屏初始化失败")
        sys.exit(1)
    if not screen.output.initialization():
        print("屏幕输出初始化失败")
        sys.exit(1)
    try:
        assert screen.input.device is not None
        screen.input.device.grab()
        print(f"[输入] 已独占 {screen.input.device_path}")
    except Exception as e:
        print(f"[输入] 独占触摸设备失败 {e}")
    fonts = load_fonts()
    current = {"page": "home"}
    show_page("home")

    # 检查更新
    def _check_update_on_start():
        try:
            from api.lapi import check_update, UpdateError
        except Exception as e:
            print(f"[更新] 模块导入失败:{type(e).__name__}: {e}")
            return
        try:
            new_build = check_update()
        except Exception as e:
            print(f"[更新] 检查失败:{e}")
            return
        if new_build <= BUILD:
            print(f"[更新] 已为最新版本(build {BUILD})")
            return
        print(f"[更新] 发现新版本 build 号 {new_build}(当前 {BUILD})")
        try:
            assert screen is not None
            screen.output.show(draw_popup([f"发现新版本 kComics {VERSION}({new_build})"]),
                                is_flashing=True)
        except OSError as e:
            print(f"[输出] 更新弹窗失败:{e}")
        time.sleep(3)
        if current["page"] == "home":
            show_page("home")
    if config.get_check_update():
        threading.Thread(target=_check_update_on_start, daemon=True).start()

    # 页面路由
    def _goto(page):
        if page == "favorites":
            favorites.load_first(screen, fonts)
        if page == "settings":
            settings.refresh_size(screen, fonts)
        current["page"] = page
        show_page(page)

    # 页面分发
    def on_gesture(data):
        handler = PAGES[current["page"]][1]
        action = handler(data, screen, fonts)
        if action is None:
            return
        if action == "exit":
            try:
                assert screen is not None
                screen.output.show(draw_popup("正在退出kComics"))
            except OSError as e:
                print(f"[输出] 弹窗刷新失败:{e}")
            print("正在退出kComics")
            time.sleep(0.5)
            sys.exit(0)
        if action in PAGES:
            _goto(action)
        else:
            print(f"[输入] 未识别的动作:{action}")

    # 更新当前页并渲染
    def _navigate(page):
        _goto(page)
    search.set_navigate(_navigate)
    result.set_navigate(_navigate)
    favorites.set_navigate(_navigate)
    info.set_active_check(lambda: current["page"] == "info")
    try:
        screen.input.listen(on_gesture=on_gesture)
    except KeyboardInterrupt:
        print("正在退出")

if __name__ == "__main__":
    main()
