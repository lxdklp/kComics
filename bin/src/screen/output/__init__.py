# 屏幕输出

from .framebuffer import EInkDisplay, FLAG, UPDATE, WAVEFORM

# 屏幕输出, EPDC framebuffer 显示
class ScreenOutput:
    def __init__(self, screen):
        self.screen = screen
        self.display = None

    # 初始化
    def initialization(self, fb_path="/dev/fb0", **kwargs):
        try:
            self.display = EInkDisplay(fb_path, **kwargs)
        except (OSError, PermissionError) as e:
            print(f"[输出] framebuffer 初始化失败:{e}")
            return None
        print(f"[输出] 已打开 {fb_path} 分辨率={self.display.width}x{self.display.height} "
            f"bpp={self.display.bpp}")
        return True

    @property
    # 屏幕分辨率
    def resolution(self):
        assert self.display is not None
        return (self.display.width, self.display.height)

    # 显示图像 默认全屏 GC16 刷新
    def show(self, image, is_flashing=True, waveform_mode=WAVEFORM.GC16,
            dither=False, region=None):
        if self.display is None:
            return None
        return self.display.show(image, is_flashing, waveform_mode, dither, region)

    # 清屏
    def clear(self):
        from PIL import Image
        img = Image.new("L", self.resolution, 255)
        return self.show(img)