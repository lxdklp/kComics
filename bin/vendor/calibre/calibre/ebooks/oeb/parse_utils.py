# calibre.ebooks.oeb.parse_utils shim (minimal, lxml-based).
import re

from lxml import etree

XHTML_NS = 'http://www.w3.org/1999/xhtml'
XML_NS = 'http://www.w3.org/XML/1998/namespace'


def XHTML(tag):
    return '{%s}%s' % (XHTML_NS, tag)


def XPath(expr):
    return etree.XPath(expr, namespaces={'h': XHTML_NS, 'svg': 'http://www.w3.org/2000/svg'})


def namespace(tag):
    """Return the namespace of a tag, if any."""
    if tag is None:
        return None
    if not isinstance(tag, str):
        tag = tag.tag
    if tag.startswith('{'):
        return tag[1:tag.index('}')]
    return None


def barename(tag):
    """Return the tag with any namespace prefix removed."""
    if tag is None:
        return tag
    if not isinstance(tag, str):
        tag = tag.tag
    if tag.startswith('{'):
        return tag.rpartition('}')[-1]
    return tag


class NotHTML(Exception):
    pass


def parse_html(raw, log=None, decoder=None, filename=None, line_numbers=False, parser=None):
    """Parse raw HTML into an lxml element tree (XHTML namespaced)."""
    if isinstance(raw, bytes):
        raw = raw.decode('utf-8', 'replace')
    if parser is None:
        parser = etree.HTMLParser(remove_comments=False, no_network=True)
    root = etree.fromstring('<html xmlns="%s">%s</html>' % (XHTML_NS, raw), parser)
    return root


def parse_xhtml(raw, decoder=None, filename=None, log=None, line_numbers=False):
    return parse_html(raw, log=log)
