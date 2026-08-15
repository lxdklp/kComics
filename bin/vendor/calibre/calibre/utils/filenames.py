# calibre.utils.filenames shim.
import os
import re


def ascii_filename(name):
    """Return a version of name containing only ASCII and filename-safe chars."""
    name = re.sub(r'[^\x20-\x7e]', '_', name)
    name = name.replace(' ', '_')
    for ch in '\\/:*?"<>|':
        name = name.replace(ch, '_')
    name = name.strip('._') or 'Unknown'
    return name[:50]


def get_unicode_name_from_path(path):
    return os.path.basename(path)


def sanitize_file_name(name, lower=False):
    if not isinstance(name, str):
        name = str(name)
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', name)
    name = name.strip()
    return name.lower() if lower else name


def url2path(path):
    return path
