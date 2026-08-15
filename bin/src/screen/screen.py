"""
    from screen import Screen

    screen = Screen()
    screen.input.initialization()           # 初始化触摸屏(自动识别)
    screen.output.initialization()          # 初始化 framebuffer 输出
    screen.output.show(image)               # 显示一张 Pillow 图像
    screen.input.listen(on_gesture=handler) # 事件循环,handler 收到 get() 字典
"""

from .input.screen import ScreenInput
from .output import ScreenOutput

# 屏幕类, input (触摸输入)与 output (显示输出)
class Screen:
    def __init__(self):
        self.input = ScreenInput(self)
        self.output = ScreenOutput(self)