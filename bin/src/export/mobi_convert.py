import os
import sys
import types
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Optional, SupportsIndex
from urllib.parse import urljoin

_VENDOR_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'vendor')
_VENDOR_CALIBRE = os.path.join(_VENDOR_ROOT, 'calibre')

def _ensure_import_paths():
    if _VENDOR_CALIBRE not in sys.path:
        sys.path.insert(0, _VENDOR_CALIBRE)
    for mod in ('lxml', 'css_parser'):
        try:
            __import__(mod)
        except ImportError:
            if _VENDOR_ROOT not in sys.path:
                sys.path.insert(0, _VENDOR_ROOT)
            break


_ensure_import_paths()

from lxml import etree  # type: ignore[attr-defined]  # noqa: E402

from calibre.ebooks.mobi.writer2.main import MobiWriter  # noqa: E402
from calibre.ebooks.mobi.writer2.resources import Resources  # noqa: E402
from calibre.ebooks.mobi.writer8.main import create_kf8_book  # noqa: E402
from calibre.ebooks.oeb.base import XHTML, XHTML_MIME, XHTML_NS  # noqa: E402
from calibre.utils.logging import Log  # noqa: E402

# Open EBook 对象模型
class OEBItem:
    def __init__(self, id, href, media_type, data, linear=True):
        self.id = id
        self.href = href
        self.media_type = media_type
        self.data = data
        self.spine_position = None
        self.is_remote = False
        self.linear = linear
    def abshref(self, href):
        return urljoin(self.href, href)
    def relhref(self, href):
        return href
    def unload_data_from_memory(self):
        self.data = None
    def load_data(self):
        pass
    def __repr__(self):
        return f'<OEBItem {self.id} {self.href} {self.media_type}>'

# Open EBook Spine 对象模型
class OEBSpine(list):
    def __init__(self, items=()):
        super().__init__(items)
        self.page_progression_direction: Optional[str] = None
    def add(self, item, linear=True):
        self.append(item)
        item.spine_position = len(self) - 1
        item.linear = linear
    def insert(self, index, item, linear=True):
        list.insert(self, index, item)
        item.spine_position = index
        item.linear = linear
    def remove(self, item):
        list.remove(self, item)
    def index(self, item, start: SupportsIndex = 0,
                stop: Optional[SupportsIndex] = None):
        try:
            return list.index(self, item, start,
                                len(self) if stop is None else stop)
        except ValueError:
            return -1

# Open EBook Manifest 对象模型
class OEBManifest(dict):
    def __init__(self, items=()):
        super().__init__((i.id, i) for i in items)
        self.ids = self
        self.hrefs = {i.href: i for i in items}
    def add(self, id, href, media_type, data=None):
        item = OEBItem(id, href, media_type, data)
        self[id] = item
        self.hrefs[href] = item
        return item
    def remove(self, item):
        self.pop(item.id, None)
        self.hrefs.pop(item.href, None)
    def generate(self, prefix, href):
        i = 1
        while f'{prefix}{i}' in self:
            i += 1
        return f'{prefix}{i}', f'{prefix}{i}.xhtml'
    def values(self):  # type: ignore[override]
        return list(super().values())
    def __iter__(self):
        return iter(super().values())

# 生成 ASIN
def _make_asin():
    return 'B0' + uuid.uuid4().hex[:8].upper()

# Open EBook Metadata 对象模型
class OEBMetadata(types.SimpleNamespace):
    def __init__(self, title, language='zh', page_progression_direction='ltr',
                resolution='1264x1680', asin=None):
        super().__init__()
        self._data = {}
        self._data['title'] = [title]
        self._data['language'] = [language]
        self._data['date'] = [datetime.now(timezone.utc).isoformat()]
        self._data['timestamp'] = self._data['date']
        self._data['identifier'] = [_Identifier('uuid', asin or _make_asin())]
        self._data['cover'] = []
        self._data['fixed_layout'] = ['true']
        self._data['book_type'] = ['comic']
        self._data['orientation_lock'] = ['portrait']
        self._data['original_resolution'] = [resolution]
        self._data['zero_gutter'] = ['true']
        self._data['zero_margin'] = ['true']
        self._data['comic_132'] = ['false']
        self.page_progression_direction = page_progression_direction
        self.primary_writing_mode = None
        self.publication_type = None
    def __getitem__(self, key):
        return self._data[key]
    def __setitem__(self, key, val):
        self._data[key] = val
    def __iter__(self):
        return iter(self._data)
    def __contains__(self, key):
        return key in self._data
    def get(self, key, default=None):
        return self._data.get(key, default)
    @property
    def title(self):
        return self._data['title']
    @property
    def language(self):
        return self._data['language']
    @property
    def rights(self):
        return self._data.get('rights', [])
    @property
    def cover(self):
        return self._data['cover']

# Identifier 对象模型
class _Identifier:
    def __init__(self, scheme, value):
        self.scheme = scheme
        self.value = value
    def __str__(self):
        return self.value
    def get(self, key, default=None):
        return self.scheme

class GuideRef:
    def __init__(self, href, title, type):
        self.href = href
        self.title = title
        self.type = type

class OEBGuide(dict):
    def add(self, name, title, href):
        self[name] = GuideRef(href, title, name)
    def remove(self, name):
        self.pop(name, None)

class OEBToc:
    def count(self):
        return 0
    def iterdescendants(self):
        return iter([])
    def __iter__(self):
        return iter([])
    def __len__(self):
        return 0

class SimpleOptions(types.SimpleNamespace):
    def __init__(self):
        super().__init__(
            no_inline_toc=True,
            toc_title=None,
            mobi_toc_at_start=False,
            extra_css='',
            mobi_periodical=False,
            dont_compress=False,
            mobi_passthrough=False,
            expand_css=False,
            mobi_keep_original_images=True,
            prefer_author_sort=False,
            share_not_sync=False,
            extract_to=None,
        )

# 生成单页 XHTML
def _page_doc(title, img_src, page_number, view_w=1264, view_h=1680, img_w=None, img_h=None):
    w = int(img_w) if img_w else int(view_w)
    h = int(img_h) if img_h else int(view_h)
    body = ('<?xml version="1.0" encoding="utf-8"?>\n'
            f'<html xmlns="{XHTML_NS}">\n'
            f'  <head><title>{_escape(title)} - {page_number}</title>\n'
            f'    <meta name="viewport" content="width={int(view_w)},height={int(view_h)}"/>\n'
            '  </head>\n'
            f'  <body style="margin:0;padding:0;background:#FFFFFF">\n'
            f'    <div style="position:relative;width:{int(view_w)}px;height:{int(view_h)}px">\n'
            f'      <img src="{_escape(img_src)}" alt="" '
            f'style="position:absolute;left:0;right:0;top:0;bottom:0;'
            f'margin:auto;width:{w}px;height:{h}px"/>\n'
            '    </div>\n'
            '  </body>\n'
            '</html>')
    return etree.fromstring(body.encode('utf-8'), parser=etree.XMLParser(recover=True))

def _escape(text):
    return (text or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

# 图片扩展名
_MIME_EXT = {'image/jpeg': 'jpg', 'image/png': 'png', 'image/gif': 'gif'}

# 读取一页图片并识别格式(WebP 转 JPEG). 只保留一页的字节,用完即弃.
def _read_page(path):
    with open(path, 'rb') as f:
        data = f.read()
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        from PIL import Image
        import io as _io
        img = Image.open(_io.BytesIO(data))
        img.load()
        with _io.BytesIO() as buf:
            img.convert('RGB').save(buf, 'JPEG', quality=88)
            data = buf.getvalue()
        return 'image/jpeg', data
    if data[:2] == b'\xff\xd8':
        return 'image/jpeg', data
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return 'image/png', data
    if data[:6] in (b'GIF87a', b'GIF89a'):
        return 'image/gif', data
    raise ValueError(f'无法识别的图片格式:{os.path.basename(path)}')

# 将图片等比缩放到屏幕内.
# 快速路径:JPEG 且不超屏时零解码原样返回(只读头部尺寸,不占位图内存).
# 转码路径:解码后立即释放 BytesIO 复制缓冲与解码器,峰值只保持一页.
def _fit_to_screen(mime, data, view_w, view_h, grayscale=True, jpeg_quality=70):
    from PIL import Image
    import io as _io
    src = _io.BytesIO(data)
    img = Image.open(src)
    w, h = img.size
    scale = min(1.0, view_w / w, view_h / h)
    if scale >= 1.0 and mime == 'image/jpeg':
        img.close()
        return mime, data, w, h
    img.load()
    src.close()
    if scale < 1.0:
        w, h = max(1, int(w * scale)), max(1, int(h * scale))
        w, h = min(w, view_w), min(h, view_h)
        img = img.resize((w, h), Image.Resampling.LANCZOS)
    if grayscale:
        if img.mode != 'L':
            img = img.convert('L')
    elif img.mode not in ('RGB', 'L'):
        img = img.convert('RGB')
    buf = _io.BytesIO()
    img.save(buf, 'JPEG', quality=jpeg_quality)
    img.close()
    return 'image/jpeg', buf.getvalue(), w, h

# 解析 "宽x高" 分辨率字符串
def parse_resolution(resolution):
    res = (resolution or '1264x1680').lower().replace('x', 'x')
    parts = res.split('x')
    try:
        return int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        return 1264, 1680

# 组装 OEB 骨架
def _setup_oeb(title, rtl, resolution, asin):
    view_w, view_h = parse_resolution(resolution)
    res_str = f'{view_w}x{view_h}'
    log = Log()
    opts = SimpleOptions()
    oeb = types.SimpleNamespace()
    oeb.log = log
    oeb.logger = log
    oeb.metadata = OEBMetadata(title, language='zh',
                                page_progression_direction='rtl' if rtl else 'ltr',
                                resolution=res_str, asin=asin)
    oeb.spine = OEBSpine()
    oeb.spine.page_progression_direction = 'rtl' if rtl else 'ltr'
    oeb.manifest = OEBManifest()
    oeb.guide = OEBGuide()
    oeb.toc = OEBToc()
    return oeb, opts, view_w, view_h

# 单页任务:读盘 + 转码(在并发 worker 中执行,返回转码完成的图数据)
def _page_worker(path, view_w, view_h, grayscale, jpeg_quality):
    mime, data = _read_page(path)
    return _fit_to_screen(mime, data, view_w, view_h, grayscale, jpeg_quality)

# 转码结果落盘(原子写),确认落盘成功后才删除 download 原图
def _save_ready_page(src, dst, data):
    tmp = dst + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(data)
    os.replace(tmp, dst)
    if os.path.getsize(dst) != len(data):
        raise IOError(f"{dst} 落盘校验失败")
    os.remove(src)

# 转码一批页并落盘到 out_dir(按页序命名):处理图片阶段.
# - 每页确认落盘成功后删除原图;失败页保留原图并记数,不产出残缺书
# - workers>1 时用线程池并行转码(PIL 的 C 层释放 GIL,双核真并行),主线程按序消费
# - progress(i, total) 跟随真实逐页处理回调,页序号从 1 起
# 返回 (首页转码结果 (mime, data) 供封面, 失败页数)
def transcode_pages(paths, out_dir, view_w, view_h, grayscale=True, jpeg_quality=70,
                    workers=1, progress=None):
    os.makedirs(out_dir, exist_ok=True)
    first = [None]
    failed = [0]
    total = len(paths)

    def _commit(i, path, mime, data):
        if first[0] is None:
            first[0] = (mime, data)
        try:
            _save_ready_page(path, os.path.join(out_dir, f"{i:04d}.jpg"), data)
        except Exception as e:
            failed[0] += 1
            print(f"[转码] 第{i}页落盘失败(已保留原图):{type(e).__name__}: {e}")
            return
        if progress:
            progress(i, total)

    if workers > 1 and total > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(_page_worker, p, view_w, view_h, grayscale, jpeg_quality)
                    for p in paths]
            for i, fut in enumerate(futs, 1):
                try:
                    mime, data, _w, _h = fut.result()
                except Exception as e:
                    failed[0] += 1
                    print(f"[转码] 第{i}页处理失败(已保留原图):{type(e).__name__}: {e}")
                    continue
                _commit(i, paths[i - 1], mime, data)
    else:
        for i, p in enumerate(paths, 1):
            try:
                mime, data, _w, _h = _page_worker(p, view_w, view_h, grayscale, jpeg_quality)
            except Exception as e:
                failed[0] += 1
                print(f"[转码] 第{i}页处理失败(已保留原图):{type(e).__name__}: {e}")
                continue
            _commit(i, p, mime, data)
    return first[0], failed[0]

# 往 OEB 里追加一页(页面 XHTML + 图片资源)
def _add_page(oeb, i, title, mime, data, view_w, view_h, grayscale, jpeg_quality):
    mime, data, img_w, img_h = _fit_to_screen(mime, data, view_w, view_h,
                                              grayscale, jpeg_quality)
    ext = _MIME_EXT.get(mime, 'jpg')
    img_href = f'images/img{i:04}.{ext}'
    page_href = f'page{i:04}.xhtml'
    item = OEBItem(f'page{i}', page_href, XHTML_MIME,
                    _page_doc(title, img_href, i, view_w, view_h, img_w, img_h))
    oeb.manifest[item.id] = item
    oeb.manifest.hrefs[page_href] = item
    oeb.spine.append(item)
    img_id = 'cover' if i == 1 else f'img{i}'
    img_item = OEBItem(img_id, img_href, mime, data)
    oeb.manifest[img_item.id] = img_item
    oeb.manifest.hrefs[img_item.href] = img_item

# 收尾:KF8 联合 MOBI 写出
def _finish_writer(oeb, opts, title, author, asin, out_path, tmp_dir):
    oeb.metadata['cover'] = ['cover']
    oeb.guide['cover'] = GuideRef(f'images/img0001', 'Cover', 'cover')
    if author:
        oeb.metadata['creator'] = [author]
    resources = Resources(oeb, opts, is_periodical=False, add_fonts=False)
    kf8 = create_kf8_book(oeb, opts, resources, for_joint=True)
    writer = MobiWriter(opts, resources, kf8, write_page_breaks_after_item=True)
    if out_path:
        writer(oeb, out_path)
        return None
    import tempfile
    fd, tmp = tempfile.mkstemp(suffix='.mobi', dir=tmp_dir or tempfile.gettempdir())
    os.close(fd)
    try:
        writer(oeb, tmp)
        with open(tmp, 'rb') as f:
            data = f.read()
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    return data

# 生成 MOBI 文件(内存中已有全部页面数据时使用)
def build_mobi(pages, title, author='', rtl=True, resolution=None, out_path=None,
                tmp_dir=None, asin=None, grayscale=True, jpeg_quality=70):
    oeb, opts, view_w, view_h = _setup_oeb(title, rtl, resolution, asin)
    for i, (mime, data) in enumerate(pages, 1):
        _add_page(oeb, i, title, mime, data, view_w, view_h, grayscale, jpeg_quality)
    return _finish_writer(oeb, opts, title, author, asin, out_path, tmp_dir)

# 生成 MOBI 文件(从磁盘路径逐页流式读取,内存只保留一页原始字节 + 转码后全量)
def build_mobi_from_paths(paths, title, author='', rtl=True, resolution=None,
                            out_path=None, tmp_dir=None, asin=None,
                            grayscale=True, jpeg_quality=70, progress=None):
    """逐页处理;progress(i, total) 在真实读页+转码后回调,页序号从 1 起."""
    oeb, opts, view_w, view_h = _setup_oeb(title, rtl, resolution, asin)
    for i, path in enumerate(paths, 1):
        mime, data = _read_page(path)
        _add_page(oeb, i, title, mime, data, view_w, view_h, grayscale, jpeg_quality)
        if progress:
            progress(i, len(paths))
    return _finish_writer(oeb, opts, title, author, asin, out_path, tmp_dir)
