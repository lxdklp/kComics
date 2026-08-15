# calibre.ebooks.oeb.normalize_css shim.
# The real calibre condenses/rewrites CSS through css_parser. For the comic
# output our CSS is tiny; we keep the sheet untouched.
def condense_sheet(sheet, use_single_rules=False, keep_important=False):
    return sheet


def run_css_cleanups(sheet, log=None, opts=None):
    return sheet
