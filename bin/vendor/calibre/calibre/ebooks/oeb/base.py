# calibre.ebooks.oeb.base shim.
# Provides the constants and helpers that the copied calibre.ebooks.mobi.writer8
# / writer2 pipeline imports from calibre.ebooks.oeb.base.
import re
from urllib.parse import urldefrag, urlparse

from lxml import etree

from calibre.ebooks.oeb.parse_utils import XHTML, XHTML_NS, XPath, barename, namespace, parse_html

XML_NS = 'http://www.w3.org/XML/1998/namespace'
XHTML_MIME = 'application/xhtml+xml'
SVG_MIME = 'image/svg+xml'
CSS_MIME = 'text/css'
OEB_CSS_MIME = 'text/x-oeb1-css'
GIF_MIME = 'image/gif'
JPEG_MIME = 'image/jpeg'
PNG_MIME = 'image/png'
WEBP_MIME = 'image/webp'
OEB_DOC_MIME = 'text/x-oeb1-document'
OPF2_NS = 'http://www.idpf.org/2007/opf'
OPF_NS = OPF2_NS
NCX_NS = 'http://www.daisy.org/z3986/2005/ncx/'
EPUB_NS = 'http://www.idpf.org/2007/ops'
EPUB2_NS = 'http://www.idpf.org/2007/ops'

OEB_DOCS = {XHTML_MIME, 'text/html', OEB_DOC_MIME, 'text/x-oeb-document'}
OEB_STYLES = {CSS_MIME, OEB_CSS_MIME, 'text/x-oeb-css', 'xhtml/css'}
OEB_RASTER_IMAGES = {GIF_MIME, JPEG_MIME, PNG_MIME, WEBP_MIME}
OEB_IMAGES = {GIF_MIME, JPEG_MIME, PNG_MIME, SVG_MIME}

XPNSMAP = {
    'h': XHTML_NS,
    'x': 'http://www.w3.org/1999/xhtml',
    'xml': XML_NS,
    'opf': OPF2_NS,
    'ncx': NCX_NS,
    'epub': EPUB_NS,
}


def OPF(name):
    return '{%s}%s' % (OPF2_NS, name)


def XHTML_MIME_(ext):
    return XHTML_MIME


def extract(elem):
    """Remove elem from its tree; join its tail to the previous element/parent."""
    parent = elem.getparent()
    if parent is not None:
        if elem.tail:
            previous = elem.getprevious()
            if previous is None:
                parent.text = (parent.text or '') + elem.tail
            else:
                previous.tail = (previous.tail or '') + elem.tail
        parent.remove(elem)
    return None


def urlnormalize(href):
    """Convert a URL into normalized form (backslashes -> slashes)."""
    if not isinstance(href, str):
        href = str(href)
    try:
        parts = urlparse(href)
    except ValueError:
        return href
    if not parts.scheme or parts.scheme == 'file':
        path, frag = urldefrag(href)
        parts = ('', '', path, '', '', frag)
    scheme, netloc, path, params, query, frag = (p or '' for p in parts)
    path = path.replace('\\', '/')
    if scheme:
        return '%s://%s%s%s%s%s' % (scheme, netloc, path,
                                    (';' + params) if params else '',
                                    ('?' + query) if query else '',
                                    ('#' + frag) if frag else '')
    return '%s%s%s%s' % (path,
                         (';' + params) if params else '',
                         ('?' + query) if query else '',
                         ('#' + frag) if frag else '')


def css_text(x):
    ans = x.cssText
    if isinstance(ans, bytes):
        ans = ans.decode('utf-8', 'replace')
    return ans


def xml2text(elem):
    from lxml import etree as _e
    return _e.tostring(elem, method='text', encoding='unicode')


QNAME_RE = re.compile(r'^[{][^{}]+[}][^{}]+$')


def isqname(name):
    return name and QNAME_RE.match(name) is not None


def prefixname(name, nsrmap):
    if not isqname(name):
        return name
    ns = namespace(name)
    if ns not in nsrmap:
        return name
    prefix = nsrmap[ns]
    if not prefix:
        return barename(name)
    return ':'.join((prefix, barename(name)))
