# evdev 设备访问
from evdev import InputDevice, list_devices

# 返回所有输入设备的 [(设备路径, 设备名), ...] 列表
def list_input_devices():
    return [(path, InputDevice(path).name) for path in list_devices()]


def open_device(path):
    return InputDevice(path)


def read_loop(device, handle_event, on_error=None):
    """把 `device` 的每个事件转发给 `handle_event`
    """
    try:
        for ev in device.read_loop():
            handle_event(ev)
    except PermissionError:
        if on_error is not None:
            on_error("权限不足")
        else:
            raise