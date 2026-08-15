import os
import sys
import types
import uuid
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

# 将图片等比缩放到屏幕内
def _fit_to_screen(mime, data, view_w, view_h):
    from PIL import Image
    import io as _io
    img = Image.open(_io.BytesIO(data))
    img.load()
    w, h = img.size
    scale = min(1.0, view_w / w, view_h / h)
    if scale < 1.0:
        w, h = max(1, int(w * scale)), max(1, int(h * scale))
        w, h = min(w, view_w), min(h, view_h)
        img = img.resize((w, h), Image.Resampling.LANCZOS)
    if img.mode not in ('RGB', 'L'):
        img = img.convert('RGB')
    buf = _io.BytesIO()
    img.save(buf, 'JPEG')
    return 'image/jpeg', buf.getvalue(), w, h

# 生成 MOBI 文件
def build_mobi(pages, title, author='', rtl=True, resolution=None, out_path=None,
                tmp_dir=None, asin=None):
    res = (resolution or '1264x1680').lower().replace('x', 'x')
    parts = res.split('x')
    try:
        view_w, view_h = int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        view_w, view_h = 1264, 1680
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
    # 每页一个独立 spine 文件
    _MIME_EXT = {'image/jpeg': 'jpg', 'image/png': 'png', 'image/gif': 'gif'}
    for i, (mime, data) in enumerate(pages, 1):
        if isinstance(mime, bytes):
            mime = mime.decode('ascii', 'replace')
        mime, data, img_w, img_h = _fit_to_screen(mime, data, view_w, view_h)
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
