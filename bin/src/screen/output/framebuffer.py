"""e-ink 屏幕输出:Pillow 图像渲染与 EPDC framebuffer 刷新.
实现参考:KOReader,fbink,感谢原仓库的贡献者
    - mxcfb:标准 i.MX EPDC(KOA/KT/KP 等),MXCFB_SEND_UPDATE = _IOW('F', 0x46)
    - mtk:MTK hwtcon(Paperwhite 4 = Bellatrix 等),ioctl 号不同:
        MXCFB_SEND_UPDATE_MTK          = _IOW('F', 0x2E, 96)
        MXCFB_WAIT_FOR_UPDATE_COMPLETE = _IOWR('F', 0x2F, 8)  (marker_data 结构体)
        MXCFB_SET_PWRDOWN_DELAY        = _IOW('F', 0x30, 4)
        MXCFB_WAIT_FOR_UPDATE_SUBMISSION = _IOW('F', 0x37, 4)
        波形/标志枚举也与 mxcfb 不同(AUTO=257,REAGL=4 等).
        定义来源:FBInk eink/mtk-kindle.h(PW6 内核 hwtcon_ioctl_cmd.h)

通过 EInkDisplay(protocol=...) 选择协议,ioctl 编号按结构体 sizeof 动态计算.
"""

import ctypes
import fcntl
import mmap
import os
import struct
import threading

# ioctl 编号宏(_IOW: dir=1, _IOWR: dir=3, type='F'=0x46)


def _iow(type_char, nr, size):
    return (1 << 30) | (ord(type_char) << 8) | nr | (size << 16)


def _iowr(type_char, nr, size):
    return (3 << 30) | (ord(type_char) << 8) | nr | (size << 16)


# -EPDC 常量(mxcfb:内核 include/linux/mxcfb.h)
# mxcfb 波形模式
class WAVEFORM:
    INIT = 0x0
    DU = 0x1
    GC16 = 0x2
    GC4 = 0x3
    A2 = 0x4
    GL16 = 0x5
    ANIM = 0x6
    AUTO = 0x7
    GL4 = 0x8
    GC8 = 0x9
    PREVIOUS = 0xE
    REAGL = 0xF

# mxcfb EPDC 刷新标志位
class FLAG:
    ENABLE_INVERSION = 0x01
    FORCE_MONOCHROME = 0x02
    ENABLE_ODD = 0x04
    ENABLE_TETRAD = 0x10
    USE_ALT_BUFFER = 0x100
    TEST_COLLISION = 0x200
    GROUP_UPDATE = 0x400
    USE_DITHERING_Y1 = 0x1000
    USE_DITHERING_Y4 = 0x2000
    USE_DITHERING = 0x3000
    USE_CMAP = 0x4000


# EPDC 常量(MTK hwtcon:FBInk eink/mtk-kindle.h)
# MTK 波形模式
class WAVEFORM_MTK:
    INIT = 0x0
    DU = 0x1
    GC16 = 0x2
    GL16 = 0x3
    REAGL = 0x4          # GLR16
    REAGLD = 0x5         # GLD16
    A2 = 0x6
    DU4 = 0x7
    GCK16 = 0x8
    GLKW16 = 0x9
    GC16_PARTIAL = 0xA
    AUTO = 0x101         # 257

# MTK EPDC 刷新标志位
class FLAG_MTK:
    ENABLE_INVERSION = 0x01
    FORCE_MONOCHROME = 0x02
    USE_CMAP = 0x04
    SKIP_CFA = 0x10
    USE_ALT_BUFFER = 0x100
    TEST_COLLISION = 0x200
    GROUP_UPDATE = 0x400
    USE_DITHERING_Y1 = 0x2000
    USE_DITHERING_Y4 = 0x4000
    USE_DITHERING = 0x6000       # Y1|Y4
    USE_REGAL = 0x8000
    ENABLE_SWIPE = 0x10000
    COLOR_NON_REGAL = 0x20000


class UPDATE:
    PARTIAL = 0x0
    FULL = 0x1


# 结构体
# mxcfb 矩形:left, top, width, height
class MxcfbRect(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_uint32),
        ("top", ctypes.c_uint32),
        ("width", ctypes.c_uint32),
        ("height", ctypes.c_uint32),
    ]
# MTK 矩形:top, left, width, height
class MxcfbRectMtk(ctypes.Structure):
    _fields_ = [
        ("top", ctypes.c_uint32),
        ("left", ctypes.c_uint32),
        ("width", ctypes.c_uint32),
        ("height", ctypes.c_uint32),
    ]

class MxcfbAltBufferData(ctypes.Structure):
    _fields_ = [
        ("phys_addr", ctypes.c_uint32),
        ("width", ctypes.c_uint32),
        ("height", ctypes.c_uint32),
        ("alt_update_region", MxcfbRect),
    ]

class MxcfbAltBufferDataMtk(ctypes.Structure):
    _fields_ = [
        ("phys_addr", ctypes.c_uint32),
        ("width", ctypes.c_uint32),
        ("height", ctypes.c_uint32),
        ("alt_update_region", MxcfbRectMtk),
    ]

class MxcfbSwipeData(ctypes.Structure):
    _fields_ = [
        ("direction", ctypes.c_uint32),
        ("steps", ctypes.c_uint32),
    ]

# MTK 设备(Paperwhite 4 等)的 update_data 结构体(96 字节)
class MxcfbUpdateData(ctypes.Structure):
    _fields_ = [
        ("update_region", MxcfbRect),
        ("waveform_mode", ctypes.c_uint32),
        ("update_mode", ctypes.c_uint32),
        ("update_marker", ctypes.c_uint32),
        ("temp", ctypes.c_int32),
        ("flags", ctypes.c_uint32),
        ("alt_buffer_data", MxcfbAltBufferData),
    ]

# MTK 设备的 update_data 结构体(96 字节)
class MxcfbUpdateDataMtk(ctypes.Structure):
    _fields_ = [
        ("update_region", MxcfbRectMtk),
        ("waveform_mode", ctypes.c_uint32),
        ("update_mode", ctypes.c_uint32),
        ("update_marker", ctypes.c_uint32),
        ("temp", ctypes.c_int32),
        ("flags", ctypes.c_uint32),
        ("dither_mode", ctypes.c_int32),
        ("quant_bit", ctypes.c_int32),
        ("alt_buffer_data", MxcfbAltBufferDataMtk),
        ("swipe_data", MxcfbSwipeData),
        ("hist_bw_waveform_mode", ctypes.c_uint32),
        ("hist_gray_waveform_mode", ctypes.c_uint32),
        ("ts_pxp", ctypes.c_uint32),
        ("ts_epdc", ctypes.c_uint32),
    ]

# MTK 设备的 update_marker_data 结构体(8 字节)
class MxcfbUpdateMarkerData(ctypes.Structure):
    _fields_ = [
        ("update_marker", ctypes.c_uint32),
        ("collision_test", ctypes.c_uint32),
    ]

# EPDC framebuffer 固定屏幕信息结构体
class FbFixScreeninfo(ctypes.Structure):
    _fields_ = [
        ("id", ctypes.c_char * 16),
        ("smem_start", ctypes.c_ulong),
        ("smem_len", ctypes.c_uint32),
        ("type", ctypes.c_uint32),
        ("type_aux", ctypes.c_uint32),
        ("visual", ctypes.c_uint32),
        ("xpanstep", ctypes.c_uint16),
        ("ypanstep", ctypes.c_uint16),
        ("ywrapstep", ctypes.c_uint16),
        ("line_length", ctypes.c_uint32),
        ("mmio_start", ctypes.c_ulong),
        ("mmio_len", ctypes.c_uint32),
        ("accel", ctypes.c_uint32),
        ("capabilities", ctypes.c_uint32),
        ("reserved", ctypes.c_uint32 * 2),
    ]


FBIOGET_VSCREENINFO = 0x4600
FBIOGET_FSCREENINFO = 0x4602

# 协议定义(ioctl 编号按结构体 sizeof 动态计算)
def _mxcfb_ioctls():
    return {
        "send_update": _iow("F", 0x46, ctypes.sizeof(MxcfbUpdateData)),
        "wait_complete": _iow("F", 0x47, 4),
        "wait_submission": _iow("F", 0x48, 4),
        "set_pwrdown_delay": _iow("F", 0x4A, 4),
    }

def _mtk_ioctls():
    return {
        "send_update": _iow("F", 0x2E, ctypes.sizeof(MxcfbUpdateDataMtk)),
        "wait_complete": _iowr("F", 0x2F, ctypes.sizeof(MxcfbUpdateMarkerData)),
        "wait_submission": _iow("F", 0x37, 4),
        "set_pwrdown_delay": _iow("F", 0x30, 4),
    }

# EPDC framebuffer 封装
class EInkDisplay:
    """EPDC framebuffer 封装:ioctl 提交更新 + Pillow 图像写入.
    protocol 可选 "mtk"(Paperwhite 4 等)或 "mxcfb"(标准 i.MX).
    MXCFB ioctl 是 32 位编码,c_uint32 对齐到 4 字节
    """
    _show_lock = threading.Lock()
    def __init__(self, fb_path="/dev/fb0", protocol="mtk",
                wait_for_submission_before=True, wait_for_completion=False,
                ioctl_timeout=5.0, temp=25, is_reagl=False, night_mode=False, alignment=8):
        self.fb_path = fb_path
        self.fd = os.open(fb_path, os.O_RDWR)
        if protocol == "mtk":
            self.update_data_cls = MxcfbUpdateDataMtk
            self.ioctls = _mtk_ioctls()
            self.W = WAVEFORM_MTK
            self.FLAG = FLAG_MTK
            self.flash_invalid_waveforms = (WAVEFORM_MTK.AUTO, WAVEFORM_MTK.DU,
                                            WAVEFORM_MTK.A2, WAVEFORM_MTK.DU4)
            self.reagl_waveform = WAVEFORM_MTK.REAGL
        elif protocol == "mxcfb":
            self.update_data_cls = MxcfbUpdateData
            self.ioctls = _mxcfb_ioctls()
            self.W = WAVEFORM
            self.FLAG = FLAG
            self.flash_invalid_waveforms = (WAVEFORM.AUTO, WAVEFORM.PREVIOUS,
                                            WAVEFORM.DU, WAVEFORM.A2)
            self.reagl_waveform = WAVEFORM.REAGL
        else:
            raise ValueError(f"未知协议: {protocol}")
        self.wait_for_submission_before = wait_for_submission_before
        self.wait_for_completion = wait_for_completion
        self.ioctl_timeout = ioctl_timeout
        self.temp = temp
        self.is_reagl = is_reagl
        self.night_mode = night_mode
        self.alignment = alignment
        self._marker = 0
        self._pending_marker = None
        self._read_screeninfo()
        self._init_epdc()
    def _init_epdc(self):
        print("[输出] EPDC 初始化:设置 powerdown 延迟 + 等待排空")
        self._ioctl(self.ioctls["set_pwrdown_delay"], ctypes.c_uint32(0), timeout=1.0)
        self.wait_update_complete(0, timeout=1.0)
    # ioctl
    def _ioctl(self, request, arg, timeout=None):
        timeout = self.ioctl_timeout if timeout is None else timeout
        result = []
        def run():
            try:
                fcntl.ioctl(self.fd, request, arg)  # type: ignore[attr-defined]
                result.append("ok")
            except OSError as e:
                result.append(e)
        t = threading.Thread(target=run, daemon=True)
        t.start()
        t.join(timeout)
        if not result:
            print(f"[输出] ioctl 0x{request:08X} 超时({timeout}s),已跳过")
            return None
        if isinstance(result[0], OSError):
            print(f"[输出] ioctl 0x{request:08X} 失败:{result[0]}")
            return None
        return True

    # 屏幕信息
    def _read_screeninfo(self):
        vbuf = ctypes.create_string_buffer(160)
        self._ioctl(FBIOGET_VSCREENINFO, vbuf, timeout=1.0)
        self.width, self.height, self.xres_virtual, self.yres_virtual, \
            _, _, self.bpp = struct.unpack_from("<7I", vbuf.raw, 0)
        print(f"[输出] framebuffer: {self.width}x{self.height} bpp={self.bpp}")
        fix = FbFixScreeninfo()
        self._ioctl(FBIOGET_FSCREENINFO, fix, timeout=1.0)
        self.smem_len = fix.smem_len
        self.line_length = fix.line_length or self.width * (self.bpp // 8)
        print(f"[输出] smem_len={self.smem_len} line_length={self.line_length}")
        self.mem = mmap.mmap(self.fd, self.smem_len, access=mmap.ACCESS_WRITE)

    # marker 管理
    def _get_next_marker(self):
        """产出 uint32 递增 marker,回绕到 1(0 留作非法值)."""
        self._marker = (self._marker + 1) & 0xFFFFFFFF
        if self._marker == 0:
            self._marker = 1
        return self._marker

    # 基础 ioctl
    def _send_update(self, x, y, w, h, waveform, update_mode, flags, marker):
        data = self.update_data_cls()
        data.update_region.top = y
        data.update_region.left = x
        data.update_region.width = w
        data.update_region.height = h
        data.waveform_mode = waveform
        data.update_mode = update_mode
        data.update_marker = marker
        data.temp = self.temp
        data.flags = flags
        if self.update_data_cls is MxcfbUpdateDataMtk:
            data.dither_mode = 1  # EPDC_FLAG_USE_DITHERING_PASSTHROUGH
            data.hist_bw_waveform_mode = self.W.REAGL if waveform == self.W.REAGL else self.W.DU
            data.hist_gray_waveform_mode = self.W.REAGL if waveform == self.W.REAGL else self.W.GC16
        return self._ioctl(self.ioctls["send_update"], data) is not None

    # 等待更新完成
    def wait_update_submission(self, marker, timeout=None):
        self._ioctl(self.ioctls["wait_submission"], ctypes.c_uint32(marker), timeout=timeout)

    # mxc_update 等待完成
    def wait_update_complete(self, marker, timeout=None):
        if self.update_data_cls is MxcfbUpdateDataMtk:
            arg = MxcfbUpdateMarkerData(update_marker=marker, collision_test=0)
        else:
            arg = ctypes.c_uint32(marker)
        self._ioctl(self.ioctls["wait_complete"], arg, timeout=timeout)

    # 唤醒 e-ink 控制器
    def poweron(self):
        self._ioctl(self.ioctls["set_pwrdown_delay"], ctypes.c_uint32(0), timeout=1.0)

    # mxc_update 提交决策
    def mxc_update(self, x, y, w, h, is_flashing, waveform_mode,
                    dither=False, night_mode=None, alignment=None):
        """对给定矩形(x,y,w,h)提交一次 e-ink 更新请求(ioctl)
        提交前后基于 waveform,dither,full/partial,night mode 做决策
        边界对齐,partial 升级为 full,dither 强制 full,waveform 提升
        flags 设置,等待策略与 marker 管理.返回本次 marker
        """
        alignment = alignment or self.alignment
        night_mode = self.night_mode if night_mode is None else night_mode
        # 1. 边界对齐
        x = (x // alignment) * alignment
        y = (y // alignment) * alignment
        w = min(self.width - x, (w // alignment) * alignment)
        h = min(self.height - y, (h // alignment) * alignment)
        if w <= 0 or h <= 0:
            return None
        update_mode = UPDATE.FULL if is_flashing else UPDATE.PARTIAL
        flags = 0
        # 2. 波形决策(对齐 FBInk):update_mode 只由 is_flashing 决定,
        #    flashing 强制 GC16 类波形;非闪屏保持请求波形(GC16+PARTIAL 无闪刷新)
        if is_flashing:
            if waveform_mode in self.flash_invalid_waveforms:
                waveform_mode = self.W.GC16
        # 3. dither / 色彩:dither 强制 FULL,REAGL 设备走色彩波形
        if dither:
            flags |= self.FLAG.USE_DITHERING
            update_mode = UPDATE.FULL
        if self.is_reagl and waveform_mode == self.W.AUTO:
            waveform_mode = self.reagl_waveform
        if night_mode:
            flags |= self.FLAG.ENABLE_INVERSION
        # 4. 等待策略
        if self.wait_for_submission_before and self._pending_marker is not None:
            self.wait_update_submission(self._pending_marker)
        # 5. 提交本次更新
        marker = self._get_next_marker()
        if not self._send_update(x, y, w, h, waveform_mode, update_mode, flags, marker):
            return None
        self._pending_marker = marker
        # 6. 等待完成
        if self.wait_for_completion:
            self.wait_update_complete(marker)
        return marker

    # 把 Pillow 图像写入 framebuffer(8bpp 灰度:0=黑 255=白)
    def write_image(self, image, x=0, y=0):
        x = max(0, min(x, self.width - 1))
        y = max(0, min(y, self.height - 1))
        iw = min(image.width, self.width - x)
        ih = min(image.height, self.height - y)
        if iw <= 0 or ih <= 0:
            return
        if self.bpp == 1:
            data = image.convert("1").tobytes()
            self.mem[0:len(data)] = data
            return
        img = image.convert("L")
        data = img.tobytes()
        for row in range(ih):
            src = row * iw
            dst = (y + row) * self.line_length + x
            self.mem[dst:dst + iw] = data[src:src + iw]
    def show(self, image, is_flashing=True, waveform_mode=WAVEFORM.GC16,
            dither=False, region=None):
        """写图并刷新屏幕.
        region=(x, y, w, h) 指定刷新区域,默认全屏.
        返回 marker,失败返回 None.
        """
        with EInkDisplay._show_lock:
            if region:
                rx, ry, rw, rh = region
            else:
                rx, ry, rw, rh = 0, 0, self.width, self.height
            self.write_image(image, rx, ry)
            return self.mxc_update(rx, ry, rw, rh, is_flashing, waveform_mode, dither=dither)