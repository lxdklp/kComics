# 分辨率适配测试：Kindle 各分辨率 × 各页面状态矩阵
# 断言：渲染无异常 + 所有绘制元素完整在屏内；代表性 handle 冒烟
# 环境变量 TEST_RESOLUTIONS（如 "1072x1448,1980x2640"）可过滤分辨率，
# 供 GitHub Actions 矩阵按分辨率拆分 job（Actions UI 直接显示每个分辨率）。
import os

import config
import pytest

from page import home, keyboard
from page.home_page import about, favorites, login, search, settings
from page.home_page.search_page import result
from page.home_page.search_page.result_page import info

from conftest import FakeScreen, assert_elements_inside

# Kindle 家族分辨率（用户指定；600×800 Kindle 10 不在支持范围，已排除）
RESOLUTIONS = [
    (1072, 1448),    # Kindle 11 / Voyage / PW3 / Oasis 1 / PW4
    (1236, 1648),    # Paperwhite 5
    (1264, 1680),    # Oasis 2/3 / Colorsoft
    (1272, 1696),    # Paperwhite 6
    (1860, 2480),    # Scribe 2022/24
    (1980, 2640),    # 2025 Scribe / Scribe Colorsoft
]

_env_res = os.environ.get("TEST_RESOLUTIONS")
if _env_res:
    RESOLUTIONS = [tuple(map(int, r.split("x"))) for r in _env_res.split(",")]

FAKE_LIST = [{"name": f"漫画名称示例{i}", "path_word": f"m{i}", "cover": ""}
             for i in range(9)]

FAKE_INFO = {
    "name": "测试漫画名称非常长用于检查标题截断效果",
    "authors": ["作者甲", "作者乙"],
    "status": "连载中",
    "updated": "2026-08-15",
    "tags": ["科幻", "冒险", "很长标签测试"],
    "brief": "这是一段简介文字，用于检查不同分辨率下简介区域的换行与溢出表现，"
             "文字内容故意写得比较长。",
    "groups": [
        {"name": "默认",
         "chapters": [{"id": f"c{i}", "name": f"第{i + 1:02d}話 测试章节"}
                      for i in range(15)]},
        {"name": "单行本",
         "chapters": [{"id": f"s{i}", "name": f"第{i + 1}卷"} for i in range(5)]},
    ],
}

_PAGE_DIMS = {}


def _screen(w, h):
    return FakeScreen(w, h)


def _render(w, h, fonts, records, mod):
    sc = _screen(w, h)
    img = mod.render(sc, fonts)
    problems = assert_elements_inside(records, w, h)
    assert not problems, f"{mod.__name__} 越界 {len(problems)} 处: {problems[:5]}"
    return img


# ---------- 主界面 ----------

@pytest.mark.parametrize("w,h", RESOLUTIONS)
def test_home_login(w, h, fonts, draw_records, monkeypatch):
    monkeypatch.setattr(config, "get_token", lambda: "tok")
    _render(w, h, fonts, draw_records, home)


@pytest.mark.parametrize("w,h", RESOLUTIONS)
def test_home_logout(w, h, fonts, draw_records, monkeypatch):
    monkeypatch.setattr(config, "get_token", lambda: "")
    _render(w, h, fonts, draw_records, home)


# ---------- 登录 / 搜索页 ----------

@pytest.mark.parametrize("w,h", RESOLUTIONS)
def test_login(w, h, fonts, draw_records):
    _render(w, h, fonts, draw_records, login)


@pytest.mark.parametrize("w,h", RESOLUTIONS)
def test_search(w, h, fonts, draw_records):
    _render(w, h, fonts, draw_records, search)


# ---------- 键盘（三种布局） ----------

def _kb_render(w, h, fonts, records, caps, pinyin="", cands=True):
    def fake_chars():
        return {"a": ["啊", "阿", "阿姨"]}
    if cands:
        keyboard.get_chars_dict = lambda: {"a": ["啊", "阿", "阿姨"]}
        keyboard.get_phrases = lambda: {"a": ["阿姨", "阿"]}
    keyboard.start(_screen(w, h), fonts, capabilities=caps, hint="测试",
                   enter_label="确定", owner="t", on_submit=lambda t: None)
    if pinyin:
        keyboard.SESSION["pinyin"] = pinyin
    return _render(w, h, fonts, records, keyboard)


@pytest.mark.parametrize("w,h", RESOLUTIONS)
def test_keyboard_en(w, h, fonts, draw_records):
    _kb_render(w, h, fonts, draw_records, ("en", "numsym"))


@pytest.mark.parametrize("w,h", RESOLUTIONS)
def test_keyboard_num(w, h, fonts, draw_records):
    _kb_render(w, h, fonts, draw_records, ("num",))


@pytest.mark.parametrize("w,h", RESOLUTIONS)
def test_keyboard_cn(w, h, fonts, draw_records):
    _kb_render(w, h, fonts, draw_records, ("cn",), pinyin="a")


# ---------- 结果页 / 收藏页（假列表） ----------

@pytest.mark.parametrize("w,h", RESOLUTIONS)
def test_result_list(w, h, fonts, draw_records, monkeypatch):
    monkeypatch.setattr(result, "_load_cover", lambda url: None)
    result.STATE.update(query="测试", list=FAKE_LIST, page=0, popup=None)
    _render(w, h, fonts, draw_records, result)


@pytest.mark.parametrize("w,h", RESOLUTIONS)
def test_favorites_list(w, h, fonts, draw_records, monkeypatch):
    monkeypatch.setattr(favorites, "_load_cover", lambda url: None)
    items = [{"name": it["name"], "path_word": it["path_word"],
              "author": "作者", "cover": ""} for it in FAKE_LIST]
    favorites.STATE.update(list=items, page=0, total=len(items), offset=0,
                           loading=False, popup=None)
    _render(w, h, fonts, draw_records, favorites)


# ---------- 详情页（假详情 + 底部 5/4 键） ----------

def _info_render(w, h, fonts, records, token):
    config.get_token = lambda: token
    info.STATE.update(item={"name": FAKE_INFO["name"],
                            "path_word": "test"},
                      info=FAKE_INFO, error=None, page=0, popup=None,
                      group=0, selected=set(), dl=None, exp=None,
                      from_page="result", is_fav=False)
    info._load_cover = lambda url: None
    return _render(w, h, fonts, records, info)


@pytest.mark.parametrize("w,h", RESOLUTIONS)
def test_info_detail_login(w, h, fonts, draw_records):
    _info_render(w, h, fonts, draw_records, "tok")


@pytest.mark.parametrize("w,h", RESOLUTIONS)
def test_info_detail_logout(w, h, fonts, draw_records):
    _info_render(w, h, fonts, draw_records, "")


# ---------- 设置页（普通 + 确认弹窗） ----------

@pytest.mark.parametrize("w,h", RESOLUTIONS)
def test_settings(w, h, fonts, draw_records, monkeypatch):
    monkeypatch.setattr(config, "get_token", lambda: "tok")
    settings.STATE.update(page=0, confirm=None, cleaning=False, popup=None,
                          dir_size=123456789, stat_loading=False,
                          library_on=True, sdr_orphans=3)
    _render(w, h, fonts, draw_records, settings)


@pytest.mark.parametrize("w,h", RESOLUTIONS)
def test_settings_confirm_clean(w, h, fonts, draw_records, monkeypatch):
    monkeypatch.setattr(config, "get_token", lambda: "tok")
    settings.STATE.update(page=0, confirm="clean", cleaning=False, popup=None,
                          dir_size=123456789, stat_loading=False,
                          library_on=True, sdr_orphans=3)
    _render(w, h, fonts, draw_records, settings)


# ---------- 关于页（鸣谢 + 弹窗） ----------

@pytest.mark.parametrize("w,h", RESOLUTIONS)
def test_about(w, h, fonts, draw_records):
    about.STATE.update(page=0, checking=False, popup=None)
    _render(w, h, fonts, draw_records, about)


@pytest.mark.parametrize("w,h", RESOLUTIONS)
def test_about_page2(w, h, fonts, draw_records):
    about.STATE.update(page=1, checking=False, popup=None)
    _render(w, h, fonts, draw_records, about)


@pytest.mark.parametrize("w,h", RESOLUTIONS)
def test_about_popup(w, h, fonts, draw_records):
    about.STATE.update(page=0, checking=False, popup=["发现新版本"])
    _render(w, h, fonts, draw_records, about)


# ---------- handle 冒烟（代表分辨率） ----------

SMOKE_RES = [(600, 800), (1264, 1680), (1980, 2640)]


@pytest.mark.parametrize("w,h", SMOKE_RES)
def test_handle_home(w, h, fonts, monkeypatch):
    monkeypatch.setattr(config, "get_token", lambda: "")
    sc = _screen(w, h)
    rect = home.button_rects(sc)["search"]
    x, y = rect[0] + rect[2] // 2, rect[1] + rect[3] // 2
    assert home.handle({"gesture": "tap", "x-pixel": x, "y-pixel": y},
                       sc, fonts) == "search"


@pytest.mark.parametrize("w,h", SMOKE_RES)
def test_handle_settings_back(w, h, fonts, monkeypatch):
    monkeypatch.setattr(config, "get_token", lambda: "")
    settings.STATE.update(page=0, confirm=None, cleaning=False, popup=None,
                          dir_size=0, stat_loading=False,
                          library_on=False, sdr_orphans=0)
    sc = _screen(w, h)
    r = settings._bottom_rects(w, h)[1]
    x, y = r[0] + r[2] // 2, r[1] + r[3] // 2
    assert settings.handle({"gesture": "tap", "x-pixel": x, "y-pixel": y},
                           sc, fonts) == "home"


@pytest.mark.parametrize("w,h", SMOKE_RES)
def test_handle_about_back(w, h, fonts):
    about.STATE.update(page=0, checking=False, popup=None)
    sc = _screen(w, h)
    r = about._bottom_rects(w, h)[1]
    x, y = r[0] + r[2] // 2, r[1] + r[3] // 2
    assert about.handle({"gesture": "tap", "x-pixel": x, "y-pixel": y},
                        sc, fonts) == "home"


@pytest.mark.parametrize("w,h", SMOKE_RES)
def test_handle_info_back(w, h, fonts, monkeypatch):
    monkeypatch.setattr(config, "get_token", lambda: "tok")
    info.STATE.update(item={"name": "x", "path_word": "test"},
                      info=FAKE_INFO, error=None, page=0, popup=None,
                      group=0, selected=set(), dl=None, exp=None,
                      from_page="result", is_fav=False)
    sc = _screen(w, h)
    from page.home_page.search_page.result_page import info as _i
    r = _i._bottom_buttons()
    assert ("返回", "back") in r
