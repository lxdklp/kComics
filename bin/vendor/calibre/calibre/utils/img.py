# calibre.utils.img shim: PIL-based replacements for the image functions the
# copied mobi writer2/writer8 pipeline uses. (Original calibre uses compiled
# calibre_extensions plus Qt; we substitute Pillow.)
from io import BytesIO

from PIL import Image, ImageOps


def image_from_data(data):
    """Return a PIL Image from raw image bytes."""
    img = Image.open(BytesIO(data))
    img.load()
    return img


def image_to_data(img, compression_quality=90, fmt='JPEG', comment=None):
    buf = BytesIO()
    fmt = (fmt or 'JPEG').upper()
    if fmt in ('JPG',):
        fmt = 'JPEG'
    if fmt == 'JPEG':
        if img.mode not in ('RGB', 'L'):
            img = img.convert('RGB')
        img.save(buf, 'JPEG', quality=compression_quality)
    else:
        img.save(buf, fmt)
    return buf.getvalue()


def png_data_to_gif_data(data):
    img = Image.open(BytesIO(data))
    img.load()
    if img.mode not in ('P', 'L', '1'):
        img = img.convert('RGB')
    buf = BytesIO()
    img.save(buf, 'GIF')
    return buf.getvalue()


def resize_image(img, width, height, compression_quality=90):
    img = img.copy()
    img.thumbnail((width, height), Image.LANCZOS)
    return img


def save_cover_data_to(data):
    """Convert image data to an RGB JPEG, flattening transparency to white."""
    img = Image.open(BytesIO(data))
    img.load()
    if img.mode not in ('RGB', 'L'):
        img = img.convert('RGBA')
        bg = Image.new('RGB', img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        img = bg
    else:
        img = img.convert('RGB')
    buf = BytesIO()
    img.save(buf, 'JPEG', quality=90)
    return buf.getvalue()


def scale_image(data, width=None, height=None, compression_quality=90):
    """Return (orig_width, orig_height, data)."""
    img = Image.open(BytesIO(data))
    img.load()
    if width and height:
        img.thumbnail((width, height), Image.LANCZOS)
    elif width:
        h = int(img.height * width / img.width)
        img = img.resize((width, h), Image.LANCZOS)
    elif height:
        w = int(img.width * height / img.height)
        img = img.resize((w, height), Image.LANCZOS)
    buf = BytesIO()
    if img.mode not in ('RGB', 'L'):
        img = img.convert('RGB')
    img.save(buf, 'JPEG', quality=compression_quality)
    return (img.width, img.height, buf.getvalue())


def image_and_format_from_data(data):
    img = Image.open(BytesIO(data))
    return img, (img.format or '').lower()


def optimize_png(path):
    img = Image.open(path)
    img.load()
    img.save(path, 'PNG', optimize=True)
