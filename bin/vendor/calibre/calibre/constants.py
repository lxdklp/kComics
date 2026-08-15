# calibre.constants shim (minimal).
import os
import sys

iswindows = os.name == 'nt'
ismacos = sys.platform == 'darwin'
islinux = not (iswindows or ismacos)

DEBUG = bool(os.environ.get('CALIBRE_DEBUG'))
__appname__ = 'calibre'
__version__ = (7, 0, 0)
filesystem_encoding = 'utf-8'

plugins = None
