# UI 布局工具
# 比例 -> 像素
def px(v, ratio):
    return int(round(v * ratio))

# (x 比例, y 比例) -> (x 像素, y 像素)
def point(w, h, xr, yr):
    return px(w, xr), px(h, yr)

#(x 比例, y 比例, 宽比例, 高比例) -> 像素矩形 (x, y, rw, rh)
def rect(w, h, xr, yr, wr, hr):
    x, y = point(w, h, xr, yr)
    return (x, y, px(w, wr), px(h, hr))
