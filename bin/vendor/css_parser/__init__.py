# css_parser shim (pure Python) for the vendored calibre writer8 pipeline.
#
# The comic pages contain no <style>/CSS, so calibre's extract_css_into_flows
# never parses real CSS. We only need the tiny surface that
# calibre/ebooks/mobi/writer8/main.py imports at module load, plus no-op
# versions of parseString/replaceUrls.
import logging
import re

log = logging.getLogger('css_parser')
log.addHandler(logging.NullHandler())


def parseString(text, validate=False, **kw):
    return Stylesheet(text)


def replaceUrls(sheet, replacer, ignoreImportRules=False, **kw):
    if hasattr(sheet, 'text') and sheet.text:
        sheet.text = re.sub(
            r'url\(\s*[\'"]?([^\'")]+)[\'"]?\s*\)',
            lambda m: f'url({replacer(m.group(1))})',
            sheet.text)
    return sheet


class Stylesheet:
    def __init__(self, text=''):
        self.text = text or ''

    @property
    def cssText(self):
        return self.text

    @property
    def cssRules(self):
        return Rules()

    def __str__(self):
        return self.cssText


class Rules:
    def rulesOfType(self, typ):
        return []


class CSSRule:
    UNKNOWN_RULE = 0
    STYLE_RULE = 1
    CHARSET_RULE = 2
    IMPORT_RULE = 3
    MEDIA_RULE = 4
    FONT_FACE_RULE = 5
    PAGE_RULE = 6
    NAMESPACE_RULE = 7
    COMMENT = 1000
