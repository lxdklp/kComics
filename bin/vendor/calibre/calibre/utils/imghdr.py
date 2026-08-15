# calibre.utils.imghdr shim: magic-byte image type detection (jpeg/png/gif/webp/bmp/tiff).
def what(filename=None, data=None):
    if data is None:
        if filename is None:
            return None
        with open(filename, 'rb') as f:
            data = f.read(32)
    data = bytes(data[:32])
    if data[:2] == b'\xff\xd8':
        return 'jpeg'
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return 'png'
    if data[:6] in (b'GIF87a', b'GIF89a'):
        return 'gif'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'webp'
    if data[:2] == b'BM':
        return 'bmp'
    if data[:4] in (b'II*\x00', b'MM\x00*'):
        return 'tiff'
    return None
