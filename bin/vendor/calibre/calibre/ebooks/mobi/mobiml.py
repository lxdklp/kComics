# calibre.ebooks.mobi.mobiml shim.
# The full MobiMLizer requires the Stylizer/flatcss css machinery, which is not
# vendored. Our comic pages are already minimal Mobipocket-compatible markup, so
# only the constants that writer2/serializer.py imports are provided.
# Original calibre code is GPLv3 (Copyright: 2008, Marshall T. Vandegrift).
from calibre.ebooks.oeb.base import XHTML_NS

MBP_NS = 'http://mobipocket.com/ns/mbp'


def MBP(name):
    return f'{{{MBP_NS}}}{name}'


MOBI_NSMAP = {None: XHTML_NS, 'mbp': MBP_NS}
