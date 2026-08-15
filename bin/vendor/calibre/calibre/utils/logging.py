# calibre.utils.logging shim.
import sys
import threading


class Log:
    def __init__(self, level=0, stream=None):
        self._level = level
        self._stream = stream or sys.stdout

    def _emit(self, level, msg, *args):
        if args:
            msg = msg % args
        try:
            print(str(msg), file=self._stream)
            self._stream.flush()
        except Exception:
            pass

    def __call__(self, msg, *args):
        self._emit('INFO', msg, *args)

    def debug(self, msg, *args):
        self._emit('DEBUG', msg, *args)

    def info(self, msg, *args):
        self._emit('INFO', msg, *args)

    def warn(self, msg, *args):
        self._emit('WARN', msg, *args)

    def error(self, msg, *args):
        self._emit('ERROR', msg, *args)

    def exception(self, msg, *args):
        self._emit('EXCEPTION', msg, *args)
        import traceback
        traceback.print_exc(file=self._stream)

    def print(self, *args, **kwargs):
        print(*args, file=self._stream, **kwargs)


class ANSIColoredLog(Log):
    pass


class default_log(Log):
    pass


class ThreadSafeLog:
    def __init__(self, log=None):
        self._lock = threading.RLock()
        self.log = log or Log()

    def __getattr__(self, name):
        with self._lock:
            return getattr(self.log, name)


def get_default_logger():
    return Log()
