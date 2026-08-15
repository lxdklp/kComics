# pytest 共享设施：假屏幕、Kindle 字体、绘制元素拦截器（用于分辨率越界检查）
import os
import sys
import types

_BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin")
sys.path.insert(0, os.path.join(_BIN, "vendor", "calibre"))
sys.path.insert(0, os.path.join(_BIN, "src"))

# 假 kcomics 模块：真实 kcomics 顶层依赖 evdev（Linux 内核），开发机/CI 不可导入
_KCOMICS = types.ModuleType("kcomics")
_KCOMICS.VERSION = "v1.0.0"
_KCOMICS.BUILD = 1
sys.modules.setdefault("kcomics", _KCOMICS)

import pytest
from PIL import Image, ImageDraw, ImageFont

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(TESTS_DIR, "STHeitiMedium.ttf")


class FakeOut:
    def __init__(self, w, h):
        self.resolution = (w, h)

    def show(self, img, is_flashing=False):
        return 1


class FakeScreen:
    def __init__(self, w, h):
        self.output = FakeOut(w, h)


@pytest.fixture
def fonts():
    """字号集 {96,48,36,28}：优先用 tests/ 内的 Kindle 真字体，缺失降级默认字体。"""
    fonts = {}
    path = FONT_PATH if os.path.exists(FONT_PATH) else None
    for size in (96, 48, 36, 28):
        try:
            fonts[size] = ImageFont.truetype(path, size)
        except OSError:
            fonts[size] = ImageFont.load_default()
    return fonts


@pytest.fixture
def draw_records(monkeypatch):
    """拦截 PIL 绘制调用，记录所有元素坐标，供渲染后越界检查。"""
    records = []
    orig_text = ImageDraw.ImageDraw.text
    orig_rr = ImageDraw.ImageDraw.rounded_rectangle
    orig_rect = ImageDraw.ImageDraw.rectangle

    def text(self, xy, text, fill=None, font=None, *a, **k):
        try:
            bbox = self.textbbox(xy, text, font=font)
        except Exception:
            bbox = (0, 0, 0, 0)
        records.append(("text", bbox, str(text)[:16]))
        return orig_text(self, xy, text, fill=fill, font=font, *a, **k)

    def rounded_rectangle(self, xy, radius=0, fill=None, outline=None,
                          width=1, *a, **k):
        records.append(("rect", tuple(xy)))
        return orig_rr(self, xy, radius=radius, fill=fill, outline=outline,
                       width=width, *a, **k)

    def rectangle(self, xy, fill=None, outline=None, width=1, *a, **k):
        records.append(("rect", tuple(xy)))
        return orig_rect(self, xy, fill=fill, outline=outline, width=width,
                         *a, **k)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", text)
    monkeypatch.setattr(ImageDraw.ImageDraw, "rounded_rectangle",
                        rounded_rectangle)
    monkeypatch.setattr(ImageDraw.ImageDraw, "rectangle", rectangle)
    return records


def assert_elements_inside(records, w, h):
    """返回越界元素列表：文本 bbox / 矩形超出屏幕的项。"""
    problems = []
    for rec in records:
        if rec[0] == "text":
            _, (x0, y0, x1, y1), text = rec
        else:
            _, (x0, y0, x1, y1) = rec
            text = ""
        if x0 < -2 or y0 < -2 or x1 > w + 2 or y1 > h + 2:
            problems.append((text or "rect", x0, y0, x1, y1))
    return problems
