# 导出链路回归:流式构建(build_mobi_from_paths)与旧接口产物一致,
# 完整 export_comic 冒烟 + 灰度化行为.
# 注意:本仓库在 Windows 沙箱下 python 无法自建新目录,测试固定使用
# tmp/exporttest/<case> 目录(该目录需预先存在;Linux/CI 无此限制,代码会自动创建).
import os
import shutil

import pytest
from PIL import Image

from export import kindle, mobi_convert

_TMP_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tmp", "exporttest")


def _case_dir(name):
    d = os.path.join(_TMP_ROOT, name)
    try:
        os.makedirs(d, exist_ok=True)
    except PermissionError:
        pytest.skip(f"沙箱未预创建目录 {d}(Windows 需预先创建)")
    try:
        for f in os.listdir(d):
            p = os.path.join(d, f)
            if os.path.isfile(p):
                os.remove(p)
            else:
                shutil.rmtree(p, ignore_errors=True)
    except (PermissionError, OSError):
        pass  # 清不掉就靠同名覆盖写容错
    return d


def _make_comic(root, chapters=2, pages=3, w=1500, h=2200):
    """在 root 下创建 downloads/测试漫画/{第N話}/xxx.jpg,返回 downloads 根目录."""
    dl = os.path.join(root, "downloads")
    comic_dir = os.path.join(dl, "测试漫画")
    os.makedirs(comic_dir, exist_ok=True)
    for ch in (f"第{i + 1}話" for i in range(chapters)):
        d = os.path.join(comic_dir, ch)
        os.makedirs(d, exist_ok=True)
        for i in range(pages):
            img = Image.new("RGB", (w, h), (i * 70, i * 110, i * 30))
            img.save(os.path.join(d, f"{i + 1:03d}.jpg"), "JPEG", quality=88)
    return dl


def test_build_mobi_from_paths_equals_build_mobi():
    """流式入口必须与逐页内存入口产生字节一致的 MOBI."""
    root = _case_dir("eq")
    dl = _make_comic(root, chapters=1)
    paths = kindle.scan_comic("测试漫画", root=dl)[0][1]
    out1 = os.path.join(root, "a.mobi")
    out2 = os.path.join(root, "b.mobi")
    asin = "B0ABC12345"
    mobi_convert.build_mobi_from_paths(paths, "测试", rtl=True,
                                       resolution="1236x1648", out_path=out1,
                                       grayscale=True, jpeg_quality=70, asin=asin)
    pages = [mobi_convert._read_page(p) for p in paths]
    mobi_convert.build_mobi(pages, "测试", rtl=True, resolution="1236x1648",
                            out_path=out2, grayscale=True, jpeg_quality=70, asin=asin)
    assert os.path.getsize(out1) > 1000
    a = open(out1, "rb").read()
    b = open(out2, "rb").read()
    # EXTH/KF8 元数据含构建时间戳,允许头部小差异;
    # 所有嵌入图片(页图 + 封面缩略图)必须逐字节一致 —— 这才是重构等价性的核心.
    assert abs(len(a) - len(b)) < 100

    def _jpegs(data):
        segs = []
        i = data.find(b'\xff\xd8\xff')
        while i >= 0:
            j = data.find(b'\xff\xd9', i)
            if j < 0:
                break
            segs.append(data[i:j + 2])
            i = data.find(b'\xff\xd8\xff', j)
        return segs

    ja, jb = _jpegs(a), _jpegs(b)
    assert len(ja) == len(jb) == 4  # 3 页 + 1 封面缩略图
    assert ja == jb


def test_export_comic_smoke():
    """export_comic 全链路:分组 → 流式构建 → 移动书库 → 清理下载.
    导出需要运行时创建临时目录,Windows 沙箱不允许时跳过(CI/Linux 正常执行)."""
    import tempfile

    root = _case_dir("smoke")
    rd = os.path.join(root, "rd")
    try:
        os.makedirs(rd, exist_ok=True)
        probe = tempfile.mkdtemp(dir=rd)
        os.rmdir(probe)
    except (PermissionError, OSError):
        pytest.skip("本机沙箱不允许导出创建临时目录")
    dl = _make_comic(root, chapters=2)
    docs = os.path.join(root, "docs")
    os.makedirs(docs, exist_ok=True)
    stages, prog = [], []
    ok, msg = kindle.export_comic(
        "测试漫画", merged=False, rtl=True, docs_dir=docs, root=dl,
        resolution="1236x1648", grayscale=True, jpeg_quality=70,
        progress=lambda d, t, n: prog.append((d, t)),
        stage_callback=lambda s, d, t, n: stages.append((s, d, t)))
    assert ok, msg
    # 三阶段顺序:build×2(每本)→ mobi×(i-1,i)×2 → move×2
    assert [s for s, _d, _t in stages] == ["build", "build",
                                            "mobi", "mobi", "mobi", "mobi",
                                            "move", "move"], stages
    # 页进度全程连续 1..6,不跳变
    assert prog == [(1, 6), (2, 6), (3, 6), (4, 6), (5, 6), (6, 6)], prog
    for name in ("测试漫画-第1話.mobi", "测试漫画-第2話.mobi"):
        p = os.path.join(docs, name)
        assert os.path.isfile(p) and os.path.getsize(p) > 1000, name
    assert not os.path.exists(os.path.join(dl, "测试漫画")), "导出成功后应清理下载目录"


def test_export_grayscale_produces_l_images():
    """灰度化应产出 L(灰度)JPEG;彩色模式保持 RGB."""
    import io

    root = _case_dir("gray")
    dl = _make_comic(root, chapters=1)
    paths = kindle.scan_comic("测试漫画", root=dl)[0][1]
    for gray, expect_mode, fname in ((True, "L", "gray.mobi"), (False, "RGB", "color.mobi")):
        out = os.path.join(root, fname)
        mobi_convert.build_mobi_from_paths(paths, "测试", rtl=True,
                                           resolution="1236x1648", out_path=out,
                                           grayscale=gray, jpeg_quality=70)
        raw = open(out, "rb").read()
        # 从 MOBI 里找第一个 JPEG SOI 段,检查解码后的 mode
        start = raw.find(b'\xff\xd8\xff')
        assert start > 0
        img = Image.open(io.BytesIO(raw[start:start + 200_000]))
        assert img.mode == expect_mode


def test_fit_to_screen_fast_path_keeps_original():
    """不超屏的 JPEG 应走零解码快速路径,返回原始字节."""
    root = _case_dir("fast")
    p = os.path.join(root, "small.jpg")
    Image.new("RGB", (800, 600), (10, 20, 30)).save(p, "JPEG", quality=80)
    data = open(p, "rb").read()
    mime, out_data, w, h = mobi_convert._fit_to_screen(
        "image/jpeg", data, 1236, 1648, grayscale=True, jpeg_quality=70)
    assert mime == "image/jpeg" and out_data is data and (w, h) == (800, 600)


def test_build_mobi_progress_callback():
    """progress 必须在真实逐页处理时回调,序列完整递增(UI 进度显示依赖)."""
    root = _case_dir("prog")
    dl = _make_comic(root, chapters=1)
    paths = kindle.scan_comic("测试漫画", root=dl)[0][1]
    calls = []
    out = os.path.join(root, "p.mobi")
    mobi_convert.build_mobi_from_paths(paths, "测试", rtl=True,
                                       resolution="1236x1648", out_path=out,
                                       grayscale=True, jpeg_quality=70,
                                       progress=lambda i, t: calls.append((i, t)))
    assert calls == [(1, 3), (2, 3), (3, 3)]


def test_transcode_writes_deletes_and_keeps_failed():
    """转码落盘:成功页确认落盘后删原图;失败页保留原图并计数."""
    root = _case_dir("tc")
    dl = _make_comic(root, chapters=1)
    chapter_dir = os.path.dirname(kindle.scan_comic("测试漫画", root=dl)[0][1][0])
    paths = kindle.scan_comic("测试漫画", root=dl)[0][1]
    bad = os.path.join(chapter_dir, "bad.txt")
    with open(bad, "w") as f:
        f.write("not an image")
    out = os.path.join(root, "out")
    first, fail = mobi_convert.transcode_pages(
        paths + [bad], out, 1236, 1648,
        grayscale=True, jpeg_quality=70, workers=1, progress=None)
    assert fail == 1                    # 坏页计失败
    assert os.path.exists(bad)          # 失败页原图保留
    assert os.path.exists(paths[1]) is False   # 成功页原图已删
    assert sorted(os.listdir(out)) == ["0001.jpg", "0002.jpg", "0003.jpg"]
    assert first is not None and first[0] == "image/jpeg"


def test_transcode_parallel_matches_single():
    """2 线程与单线程转码落盘产物必须逐字节一致."""
    root = _case_dir("pa")
    dl1 = _make_comic(os.path.join(root, "s1"), chapters=1)
    dl2 = _make_comic(os.path.join(root, "s2"), chapters=1)
    p1 = kindle.scan_comic("测试漫画", root=dl1)[0][1]
    p2 = kindle.scan_comic("测试漫画", root=dl2)[0][1]
    o1 = os.path.join(root, "o1")
    o2 = os.path.join(root, "o2")
    mobi_convert.transcode_pages(p1, o1, 1236, 1648,
                                 grayscale=True, jpeg_quality=70,
                                 workers=2, progress=None)
    mobi_convert.transcode_pages(p2, o2, 1236, 1648,
                                 grayscale=True, jpeg_quality=70,
                                 workers=1, progress=None)
    f1, f2 = sorted(os.listdir(o1)), sorted(os.listdir(o2))
    assert f1 == f2 == ["0001.jpg", "0002.jpg", "0003.jpg"]
    for n in f1:
        a = open(os.path.join(o1, n), "rb").read()
        b = open(os.path.join(o2, n), "rb").read()
        assert a == b, n
    # 两份源图都已被删除
    for dl in (dl1, dl2):
        comic = os.listdir(dl)[0]
        ch = os.listdir(os.path.join(dl, comic))[0]
        assert not os.listdir(os.path.join(dl, comic, ch))