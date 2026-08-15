"""帧缓冲快照工具:保存/恢复 /dev/fb0

用法:
    fb_snapshot.py save <file>     # 把当前屏幕内容保存到文件
    fb_snapshot.py restore <file>  # 写回文件内容并全屏刷新
"""
import os
import sys

_BIN = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_BIN, "vendor"))
sys.path.insert(0, os.path.join(_BIN, "src"))

from screen.output.framebuffer import EInkDisplay, WAVEFORM  # noqa: E402

FB_PATH = "/dev/fb0"

# 保存
def save(path):
    display = EInkDisplay(FB_PATH)
    size = display.smem_len
    data = display.mem[:size]
    with open(path, "wb") as f:
        f.write(data)
    print(f"[快照] 已保存 {size} 字节 -> {path}")

# 恢复
def restore(path):
    with open(path, "rb") as f:
        data = f.read()
    display = EInkDisplay(FB_PATH)
    if len(data) != display.smem_len:
        print(f"[快照] 文件大小 {len(data)} 与 smem_len {display.smem_len} 不符, 但是仍按文件长度写回")
    display.mem[: len(data)] = data
    print("[快照] 已写回帧缓冲,全屏刷新...")
    display.mxc_update(0, 0, display.width, display.height,
                        is_flashing=True, waveform_mode=WAVEFORM.GC16)
    print("[快照] 恢复完成")

# 主函数
def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    cmd, path = sys.argv[1], sys.argv[2]
    if cmd == "save":
        save(path)
    elif cmd == "restore":
        restore(path)
    else:
        print(f"未知命令: {cmd}")
        sys.exit(2)

if __name__ == "__main__":
    main()
