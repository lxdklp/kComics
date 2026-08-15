# calibre shim for kcomics vendored AZW3 writer.
# Provides only the minimal surface that the copied calibre.ebooks.mobi writer8 /
# writer2 pipeline needs, without the full calibre application (no compiled
# extensions, no GUI, no database).
# The original calibre code is GPLv3; the copied files carry their own headers.
import html
import re
import unicodedata
import urllib.parse


def isbytestring(x):
    return isinstance(x, bytes)


def is_string(x):
    return isinstance(x, str)


def force_unicode(x, enc='utf-8', errors='replace'):
    if isinstance(x, str):
        return x
    if isinstance(x, bytes):
        return x.decode(enc, errors)
    return str(x)


def as_unicode(x, enc='utf-8', errors='strict'):
    return force_unicode(x, enc, errors)


def unquote(x):
    return urllib.parse.unquote(x)


def replace_entities(x):
    return html.unescape(x)


def my_unichr(x):
    try:
        return chr(x)
    except (ValueError, OverflowError):
        return ''


def clean_ascii_chars(x):
    return x


def get_types_map():
    return {
        '.xhtml': 'application/xhtml+xml',
        '.html': 'text/html',
        '.htm': 'text/html',
        '.css': 'text/css',
        '.svg': 'image/svg+xml',
        '.gif': 'image/gif',
        '.jpeg': 'image/jpeg',
        '.jpg': 'image/jpeg',
        '.png': 'image/png',
        '.webp': 'image/webp',
        '.opf': 'application/oebps-package+xml',
        '.ncx': 'application/x-dtbncx+xml',
        '.txt': 'text/plain',
    }


def parse_css_color(val):
    from tinycss.color3 import parse_color_string
    return parse_color_string(val)
