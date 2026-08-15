# calibre.ptempfile shim.
import os
import tempfile


def _project_tmp_dir():
    """项目根目录/tmp（与 downloads 同级）：bin/vendor/calibre/calibre/ptempfile.py
    向上 5 级即项目根。只清内容、不删目录的临时文件统一放这里。"""
    root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
    d = os.path.join(root, 'tmp')
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        pass
    return d


class PersistentTemporaryFile:
    """A temporary file that persists after close (used by calibre's resource
    processing)."""

    def __init__(self, suffix='', prefix='', dir=None):
        if dir is None:
            dir = _project_tmp_dir()
        fd, self.name = tempfile.mkstemp(suffix=suffix, prefix=prefix, dir=dir)
        os.close(fd)

    def write(self, data):
        with open(self.name, 'wb') as f:
            f.write(data)

    def read(self):
        with open(self.name, 'rb') as f:
            return f.read()

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
