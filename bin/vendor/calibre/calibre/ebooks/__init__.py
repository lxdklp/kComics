# calibre.ebooks shim (minimal subset).
import unicodedata


class ConversionError(Exception):
    def __init__(self, msg, only_msg=False):
        Exception.__init__(self, msg)
        self.only_msg = only_msg


class UnknownFormatError(Exception):
    pass


class DRMError(ValueError):
    pass


def normalize(x):
    if isinstance(x, str):
        return unicodedata.normalize('NFC', x)
    return x


def generate_masthead(title, name=None, as_uri=False):
    """Periodical masthead image; not used for comics. Returns a small PNG."""
    from io import BytesIO
    from PIL import Image
    img = Image.new('RGB', (600, 100), (255, 255, 255))
    buf = BytesIO()
    img.save(buf, 'PNG')
    return buf.getvalue()
